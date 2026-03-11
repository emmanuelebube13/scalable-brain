import pandas as pd
from sklearn.model_selection import train_test_split, TimeSeriesSplit
from sklearn.metrics import f1_score  
import xgboost as xgb
import lightgbm as lgb
from sklearn.ensemble import RandomForestClassifier
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import joblib
import optuna
import numpy as np
import warnings
import sqlalchemy as sa
from dotenv import load_dotenv
import os
import urllib.parse

warnings.filterwarnings('ignore')

load_dotenv()
DB_SERVER = os.getenv('DB_SERVER')
DB_USER = os.getenv('DB_USER')
DB_PASS = os.getenv('DB_PASS')
DB_NAME = 'ForexBrainDB'

params = urllib.parse.quote_plus(
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={DB_SERVER};"
    f"DATABASE={DB_NAME};"
    f"UID={DB_USER};"
    f"PWD={DB_PASS}"
)
engine = sa.create_engine(f"mssql+pyodbc:///?odbc_connect={params}")

# Fetch data 
query = """
SELECT 
    fmr.Regime_Label, 
    fmr.ATR_Value, 
    fmr.ADX_Value, 
    fs.Asset_ID, 
    fs.Strategy_ID, 
    fs.Signal_Value, 
    fto.Is_Winner
FROM 
    Fact_Market_Regime fmr
INNER JOIN 
    Fact_Signals fs ON fmr.Timestamp = fs.Timestamp AND fmr.Asset_ID = fs.Asset_ID
INNER JOIN 
    Fact_Trade_Outcomes fto ON fs.Timestamp = fto.Timestamp AND fs.Asset_ID = fto.Asset_ID AND fs.Strategy_ID = fto.Strategy_ID
ORDER BY 
    fs.Timestamp ASC
"""
df = pd.read_sql(query, engine)
df = df.dropna()
df = pd.get_dummies(df, columns=['Regime_Label', 'Asset_ID', 'Strategy_ID'], drop_first=True)

X = df.drop('Is_Winner', axis=1)
y = df['Is_Winner']
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)

# Custom scorer: F1 for balanced precision/recall (focus on winners)
def custom_scorer(y_true, y_pred):
    return f1_score(y_true, y_pred)  

# Optuna objective for tuning 
def optuna_objective(trial, model_type):
    if model_type == 'xgboost':
        params = {
            'n_estimators': trial.suggest_int('n_estimators', 50, 200),
            'max_depth': trial.suggest_int('max_depth', 3, 10),
            'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3),
            'scale_pos_weight': 3  # Bias toward winners (3x weight)
        }
        model = xgb.XGBClassifier(**params, random_state=42)
    elif model_type == 'lightgbm':
        params = {
            'n_estimators': trial.suggest_int('n_estimators', 50, 200),
            'max_depth': trial.suggest_int('max_depth', 3, 10),
            'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3),
            'scale_pos_weight': 3  # Bias toward winners
        }
        model = lgb.LGBMClassifier(**params, random_state=42, verbose=-1)
    elif model_type == 'randomforest':
        params = {
            'n_estimators': trial.suggest_int('n_estimators', 50, 200),
            'max_depth': trial.suggest_int('max_depth', 3, 20),
            'class_weight': 'balanced_subsample'  
        }
        model = RandomForestClassifier(**params, random_state=42)
    
    tscv = TimeSeriesSplit(n_splits=3)
    scores = []
    for train_idx, val_idx in tscv.split(X_train):
        model.fit(X_train.iloc[train_idx], y_train.iloc[train_idx])
        pred = model.predict(X_train.iloc[val_idx])
        scores.append(custom_scorer(y_train.iloc[val_idx], pred))
    return np.mean(scores)

# Tune and train models (NO SVM!)
models = ['xgboost', 'lightgbm', 'randomforest']  
best_models = {}
for m in models:
    print(f"Starting Optuna tuning for {m}...")
    study = optuna.create_study(direction='maximize')
    study.optimize(lambda trial: optuna_objective(trial, m), n_trials=20)
    best_params = study.best_params
    
    if m == 'xgboost':
        best_params['scale_pos_weight'] = 3
        best_model = xgb.XGBClassifier(**best_params, random_state=42)
    elif m == 'lightgbm':
        best_params['scale_pos_weight'] = 3
        best_model = lgb.LGBMClassifier(**best_params, random_state=42, verbose=-1)
    elif m == 'randomforest':
        best_params['class_weight'] = 'balanced_subsample'
        best_model = RandomForestClassifier(**best_params, random_state=42)
        
    best_model.fit(X_train, y_train)
    best_models[m] = best_model
    print(f"Best {m} params: {best_params}")

# Simple LSTM (for time-series) 
class ForexDataset(Dataset):
    def __init__(self, X, y, seq_len=50):
        # CTO FIX: Float32 casting so PyTorch doesn't crash on booleans
        self.X = torch.tensor(X.astype(np.float32).values, dtype=torch.float32)
        self.y = torch.tensor(y.astype(np.float32).values, dtype=torch.float32)
        self.seq_len = seq_len

    def __len__(self):
        return len(self.y) - self.seq_len

    def __getitem__(self, idx):
        return self.X[idx:idx+self.seq_len], self.y[idx+self.seq_len]

class LSTMModel(nn.Module):
    def __init__(self, input_size, hidden_size=50, num_layers=2):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_size, 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        _, (hn, _) = self.lstm(x)
        out = self.fc(hn[-1])
        return self.sigmoid(out)

# Train LSTM 
print("Training PyTorch LSTM...")
seq_len = 50
train_dataset = ForexDataset(X_train, y_train, seq_len)
train_loader = DataLoader(train_dataset, batch_size=64, shuffle=False)
model = LSTMModel(input_size=X_train.shape[1])
optimizer = optim.Adam(model.parameters(), lr=0.001)

# CTO FIX: Batch-safe custom weighted loss
criterion = nn.BCELoss(reduction='none') 

for epoch in range(10):  
    model.train()
    for X_batch, y_batch in train_loader:
        optimizer.zero_grad()
        output = model(X_batch)
        
        # Calculate loss and apply 3x weight to the winners (1.0)
        loss = criterion(output.squeeze(), y_batch)
        weight = torch.where(y_batch == 1.0, 3.0, 1.0) 
        weighted_loss = (loss * weight).mean()
        
        weighted_loss.backward()
        optimizer.step()
        
best_models['lstm'] = model

# Evaluate all on test set
print("Evaluating all models...")
results = []
for name, model in best_models.items():
    if name == 'lstm':
        test_dataset = ForexDataset(X_test, y_test, seq_len)
        test_loader = DataLoader(test_dataset, batch_size=64, shuffle=False)
        model.eval()
        preds = []
        with torch.no_grad():
            for X_batch, _ in test_loader:
                output = model(X_batch)
                preds.extend(output.squeeze().numpy() > 0.5)
        y_pred = np.array(preds)
        acc = f1_score(y_test[seq_len:], y_pred)  
    else:
        y_pred = model.predict(X_test)
        acc = f1_score(y_test, y_pred)
    results.append({'Model': name, 'Test F1': acc})
    
print("\n=== FINAL TOURNAMENT RESULTS ===")
print(pd.DataFrame(results))

# Save best 
best_model_name = max(results, key=lambda x: x['Test F1'])['Model']
joblib.dump(best_models[best_model_name], 'models/best_ml_gatekeeper.pkl')
print(f"\nChampion model saved: {best_model_name}")
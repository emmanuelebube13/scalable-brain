import pandas as pd
from sklearn.model_selection import train_test_split, TimeSeriesSplit
from sklearn.metrics import accuracy_score
import xgboost as xgb
import lightgbm as lgb
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
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

# Fetch data (same as before)
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

# Custom scorer for optimization (maximize expectancy proxy: win rate * avg win - loss rate * avg loss)
def custom_scorer(y_true, y_pred):
    acc = accuracy_score(y_true, y_pred)
    # Proxy for R:R - assume higher acc correlates to better R:R
    return acc  # TODO: Integrate full expectancy if we add sim returns

# Optuna objective for tuning
def optuna_objective(trial, model_type):
    if model_type == 'xgboost':
        params = {
            'n_estimators': trial.suggest_int('n_estimators', 50, 200),
            'max_depth': trial.suggest_int('max_depth', 3, 10),
            'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3)
        }
        model = xgb.XGBClassifier(**params, random_state=42)
    elif model_type == 'lightgbm':
        params = {
            'n_estimators': trial.suggest_int('n_estimators', 50, 200),
            'max_depth': trial.suggest_int('max_depth', 3, 10),
            'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3)
        }
        model = lgb.LGBMClassifier(**params, random_state=42, verbose=-1)
    elif model_type == 'randomforest':
        params = {
            'n_estimators': trial.suggest_int('n_estimators', 50, 200),
            'max_depth': trial.suggest_int('max_depth', 3, 20)
        }
        model = RandomForestClassifier(**params, random_state=42)
    elif model_type == 'svm':
        params = {
            'C': trial.suggest_float('C', 0.1, 10),
            'kernel': trial.suggest_categorical('kernel', ['rbf', 'linear'])
        }
        model = SVC(**params, probability=True, random_state=42)
    # Train and score with CV
    tscv = TimeSeriesSplit(n_splits=3)
    scores = []
    for train_idx, val_idx in tscv.split(X_train):
        model.fit(X_train.iloc[train_idx], y_train.iloc[train_idx])
        pred = model.predict(X_train.iloc[val_idx])
        scores.append(custom_scorer(y_train.iloc[val_idx], pred))
    return np.mean(scores)

# Tune and train models
models = ['xgboost', 'lightgbm', 'randomforest']  # LSTM below separately
best_models = {}
for m in models:
    study = optuna.create_study(direction='maximize')
    study.optimize(lambda trial: optuna_objective(trial, m), n_trials=20)
    best_params = study.best_params
    if m == 'xgboost':
        best_model = xgb.XGBClassifier(**best_params, random_state=42)
    elif m == 'lightgbm':
        best_model = lgb.LGBMClassifier(**best_params, random_state=42, verbose=-1)
    elif m == 'randomforest':
        best_model = RandomForestClassifier(**best_params, random_state=42)
    elif m == 'svm':
        best_model = SVC(**best_params, probability=True, random_state=42)
    best_model.fit(X_train, y_train)
    best_models[m] = best_model
    print(f"Best {m} params: {best_params}")

# Simple LSTM (for time-series) - reshape to sequences (e.g., last 50 bars)
class ForexDataset(Dataset):
    def __init__(self, X, y, seq_len=50):
        # FIX: Force all data (including True/False dummies) into raw float32 numbers
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
seq_len = 50
train_dataset = ForexDataset(X_train, y_train, seq_len)
train_loader = DataLoader(train_dataset, batch_size=64, shuffle=False)
model = LSTMModel(input_size=X_train.shape[1])
optimizer = optim.Adam(model.parameters(), lr=0.001)
criterion = nn.BCELoss()
for epoch in range(10):  # Quick train
    model.train()
    for X_batch, y_batch in train_loader:
        optimizer.zero_grad()
        output = model(X_batch)
        loss = criterion(output.squeeze(), y_batch)
        loss.backward()
        optimizer.step()
best_models['lstm'] = model

# Evaluate all on test set
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
    else:
        y_pred = model.predict(X_test)
    acc = accuracy_score(y_test[seq_len:] if name == 'lstm' else y_test, y_pred)  # Adjust for seq_len
    results.append({'Model': name, 'Test Accuracy': acc})
print(pd.DataFrame(results))

# Save best (e.g., highest acc)
best_model_name = max(results, key=lambda x: x['Test Accuracy'])['Model']
joblib.dump(best_models[best_model_name], 'models/best_ml_gatekeeper.pkl')
print(f"Best model: {best_model_name}")
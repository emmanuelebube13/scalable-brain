import pandas as pd
import numpy as np
from xgboost import XGBClassifier
from sklearn.metrics import classification_report, accuracy_score
import joblib
import os

def train_xgboost(asset_id, confidence_threshold=0.65):
    print(f"🚀 Loading 1:2 R/R Dataset for Asset {asset_id}...")
    df = pd.read_csv(f'data/processed/asset_{asset_id}_ml_data_final.csv')
    
    # 1. Define Features and Target
    cols_to_drop = ['Timestamp', 'Open', 'High', 'Low', 'Close', 'Target_Class']
    X = df.drop(columns=cols_to_drop)
    
    # XGBoost strictly requires classes to be [0, 1, 2] instead of [-1, 0, 1]
    # Mapping: -1 (Sell) -> 0,  0 (Hold) -> 1,  1 (Buy) -> 2
    y = df['Target_Class'].map({-1: 0, 0: 1, 1: 2})
    
    # 2. Chronological Split (70% Train / 30% Test)
    split_idx = int(len(df) * 0.7)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    
    print("\n🧠 Training XGBoost Quant Model...")
    # Quant-Tuned Hyperparameters
    xgb_model = XGBClassifier(
        n_estimators=300,        # Number of boosting rounds
        max_depth=4,             # Keep trees shallow to prevent overfitting
        learning_rate=0.05,      # Slow learning rate for better generalization
        subsample=0.8,           # Only use 80% of data per tree (prevents memorization)
        colsample_bytree=0.8,    # Only use 80% of features per tree
        objective='multi:softprob', 
        eval_metric='mlogloss',
        random_state=42,
        n_jobs=-1
    )
    
    # Train the model
    xgb_model.fit(X_train, y_train)
    
    # 3. Confidence Thresholding (Process 3.0 from DFD)
    print(f"🔍 Executing Trades (Minimum Confidence: {confidence_threshold * 100}%)...")
    
    # Get raw probabilities for each class [Sell(0), Hold(1), Buy(2)]
    probabilities = xgb_model.predict_proba(X_test)
    
    # Default everything to Hold (1)
    y_pred_high_conf = np.ones(len(X_test)) 
    
    for i in range(len(probabilities)):
        prob_sell = probabilities[i][0]
        prob_buy = probabilities[i][2]
        
        if prob_buy >= confidence_threshold:
            y_pred_high_conf[i] = 2 # Execute Buy
        elif prob_sell >= confidence_threshold:
            y_pred_high_conf[i] = 0 # Execute Sell
            
    # 4. Evaluation
    accuracy = accuracy_score(y_test, y_pred_high_conf)
    print(f"\n=========================================")
    print(f"🎯 SYSTEM ACCURACY: {accuracy * 100:.2f}%")
    print(f"=========================================\n")
    
    print("📋 DETAILED REPORT (Focus on Precision for Buys/Sells):")
    # We map the names back to normal for readability
    target_names = ['Sell (-1)', 'Hold (0)', 'Buy (1)']
    print(classification_report(y_test, y_pred_high_conf, target_names=target_names, zero_division=0))
    
    # Calculate executed trades (Anything that is not a 1/Hold)
    executed_trades = np.count_nonzero(y_pred_high_conf != 1)
    print(f"\n🚀 Total 1:2 R/R Trades Executed: {executed_trades} out of {len(X_test)} hours.")
    
    # 5. Feature Importance
    print("\n🌟 FEATURE IMPORTANCE (What XGBoost cares about):")
    importances = xgb_model.feature_importances_
    feature_ranking = pd.DataFrame({'Feature': X.columns, 'Importance': importances})
    feature_ranking = feature_ranking.sort_values(by='Importance', ascending=False)
    feature_ranking['Importance'] = (feature_ranking['Importance'] * 100).round(2).astype(str) + '%'
    print(feature_ranking.to_string(index=False))

    # 6. Save the Model
    os.makedirs('models', exist_ok=True)
    model_path = f'models/xgboost_asset_{asset_id}_v1.pkl'
    joblib.dump(xgb_model, model_path)
    print(f"\n💾 XGBoost Brain saved to: {model_path}")

if __name__ == "__main__":
    # You can lower this to 0.55 if it takes 0 trades, or raise to 0.70 for stricter entries
    train_xgboost(5, confidence_threshold=0.75)

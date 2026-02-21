import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, accuracy_score
import joblib
import os

def train_random_forest(asset_id):
    print(f"🧠 Loading ML Dataset for Asset {asset_id}...")
    df = pd.read_csv(f'data/processed/asset_{asset_id}_ml_data_final.csv')
    
    # 1. Define Features (X) and Target (y)
    # We drop raw prices because ML models prefer standardized indicators (like RSI) over raw numbers.
    cols_to_drop = ['Timestamp', 'Open', 'High', 'Low', 'Close', 'Target_Class']
    X = df.drop(columns=cols_to_drop)
    y = df['Target_Class']
    
    # 2. Risk 2 Mitigation: 70% Training / 30% Testing Split
    # CRITICAL: shuffle=False is required for financial time-series. 
    # If we shuffle, the AI will "peek into the future" to predict the past.
    split_idx = int(len(df) * 0.7)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    
    print(f"📊 Training Data (Studying the past): {len(X_train)} hours")
    print(f"🧪 Testing Data (Trading the future): {len(X_test)} hours")
    
    # 3. Initialize the AI (The "Brain")
    print("\n🤖 Training Random Forest Classifier... (Building 100 decision trees)")
    rf_model = RandomForestClassifier(
        n_estimators=100,        # Number of trees in the forest
        random_state=42,         # Ensures we get the same results every time we run it
        class_weight='balanced', # Helps the AI pay equal attention to Buy, Sell, and Hold
        n_jobs=-1                # Uses all your Fedora machine's CPU cores for speed
    )
    
    # 4. Train the model
    rf_model.fit(X_train, y_train)
    
    # 5. The Validation Framework (Milestone 3 / Backtest)
    print("🔍 Validating Model on Unseen Testing Data...")
    y_pred = rf_model.predict(X_test)
    
    # 6. Evaluate against the Charter's >65% Target
    accuracy = accuracy_score(y_test, y_pred)
    print(f"\n=========================================")
    print(f"🎯 SYSTEM WIN RATE (ACCURACY): {accuracy * 100:.2f}%")
    print(f"=========================================\n")
    
    print("📋 DETAILED REPORT (Precision & Recall):")
    # Mapping -1 to Sell, 0 to Hold, 1 to Buy
    print(classification_report(y_test, y_pred, target_names=['Sell (-1)', 'Hold (0)', 'Buy (1)']))
    
    # 7. The Report Card: Feature Importance
    print("\n🌟 FEATURE IMPORTANCE (What the AI relies on most):")
    importances = rf_model.feature_importances_
    feature_ranking = pd.DataFrame({'Feature': X.columns, 'Importance': importances})
    feature_ranking = feature_ranking.sort_values(by='Importance', ascending=False)
    
    # Format as percentages for readability
    feature_ranking['Importance'] = (feature_ranking['Importance'] * 100).round(2).astype(str) + '%'
    print(feature_ranking.to_string(index=False))
    
    # 8. Save the Brain
    os.makedirs('models', exist_ok=True)
    model_path = f'models/rf_model_asset_{asset_id}_v1.pkl'
    joblib.dump(rf_model, model_path)
    print(f"\n💾 Scalable Brain saved to: {model_path}")

if __name__ == "__main__":
    # Train the model for EUR_USD (Asset 5)
    train_random_forest(5)

# Quant Signal Brief

Generated: 2026-04-28T07:27:51+00:00

### Azalyst Alpha Scanner Token Signals Brief

**Date:** 2026-04-28

#### Summary:
- **Evaluated Tokens:** 12
- **Hit Count:** 0
- **Hit Rate:** 0.0%

#### Detailed Analysis:

1. **USDC**
   - **Chain:** Arbitrum
   - **Scores:** pump_score = 9.13, dump_score = 67.97, anomaly_score = 100.0, smart_money_score = 0.0
   - **Classification:** Strong Short (dump_score >= 65)
   - **Reasons:** whale_distribution, ml_isolation_forest_anomaly
   - **Metrics:** price = 0.9998, liquidity_usd = 54,910,197.66, price_change_1h_pct = -0.010001, volume_1h_usd = 2,616,035.17, buy_imbalance = -0.9714, whale_net_usd = -39,437.31
   - **Biggest Risks:** Whale selling pressure, high anomaly score indicating unusual activity.
   - **False-Positive Risk:** High due to the anomaly score, but the dump score is strong.
   - **Next Confirmation:** Monitor for further whale activity and price movements.

2. **BASED**
   - **Chain:** BNB
   - **Scores:** pump_score = 0.0, dump_score = 39.34, anomaly_score = 83.81, smart_money_score = 0.0
   - **Classification:** Anomaly Watch (anomaly_score >= 70)
   - **Reasons:** risk:mintable, risk:freeze_authority, ml_isolation_forest_anomaly
   - **Metrics:** price = 0.1386, liquidity_usd = 572,327.64, price_change_1h_pct = -2.04, volume_1h_usd = 85,610.66, buy_imbalance = -0.8817
   - **Biggest Risks:** Mintable token, freeze authority risk, high anomaly score.
   - **False-Positive Risk:** Moderate due to the anomaly score and risks.
   - **Next Confirmation:** Evaluate the project's governance and community response.

3. **KIMA**
   - **Chain:** Arbitrum
   - **Scores:** pump_score = 0.0, dump_score = 5.81, anomaly_score = 75.96, smart_money_score = 0.0
   - **Classification:** Anomaly Watch (anomaly_score >= 70)
   - **Reasons:** risk:thin_liquidity, ml_isolation_forest_anomaly
   - **Metrics:** price = 0.004393, liquidity_usd = 259.46, price_change_1h_pct = -3.12, volume_1h_usd = 4.12, buy_imbalance = 0.0
   - **Biggest Risks:** Thin liquidity, high anomaly score.
   - **False-Positive Risk:** High due to the anomaly score and thin liquidity.
   - **Next Confirmation:** Monitor liquidity changes and trading volume.

4. **AIOT**
   - **Chain:** BNB
   - **Scores:** pump_score = 9.95, dump_score = 18.05, anomaly_score = 58.73, smart_money_score = 0.0
   - **Classification:** Watch (no strong criteria met)
   - **Reasons:** normal_watch
   - **Metrics:** price = 0.07639, liquidity_usd = 2,207,554.89, price_change_1h_pct = -11.89, volume_1h_usd = 304,945.13, buy_imbalance = 0.0
   - **Biggest Risks:** Significant price drop, high volume

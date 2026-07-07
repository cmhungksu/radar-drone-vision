# Counter-UAS Radar Carrier Resilience Platform

## 完整整合版 Claude Code 實作指令

## 建議專案目錄名稱

`counter-uas-radar-carrier`

## 一句話定位

本專案不是一般無人機表演系統，而是將「雷達掃描儀」、「都卜勒雷達訊號分析」、「鳥 / 無人機辨識」、「低空空域態勢感知」、「無人機矩陣航母車斗模組」、「韌性車隊」、「戰術推演遊戲化展示」整合成一套可展示、可擴充、可申請韌性計畫、可作為未來國防前段能力基礎的低空空域反無人機韌性平台。

---

# 0. 專案背景與展示目的

明天將有大型無人機公司來參觀系統。對方本身已經熟悉無人機展演、編隊飛行與無人機操控，因此本系統展示重點不能只是「我們也可以放飛很多無人機」。

本系統必須展現不同價值：

1. 我們能看見天空中的低空目標。
2. 我們能用雷達與都卜勒訊號分辨小鳥與無人機。
3. 我們能追蹤未知目標。
4. 我們能把雷達資料、影像資料、車隊資料與無人機艙位資料整合成態勢圖。
5. 我們能用無人機矩陣航母車斗模組派出本方無人機進行確認、照明、通訊中繼、災區巡查或任務支援。
6. 我們能將平時商用車、餐車、救災車、活動支援車，轉換成低空空域韌性節點。
7. 我們能用戰術推演遊戲化介面，展示反無人機場景中的雷達辨識、威脅分級、虛擬鎖定、虛擬攔截、事件回放與證據保存。

本系統展示口徑：

> 無人機公司負責讓無人機飛得漂亮，我們負責讓天空變得可辨識、可追蹤、可指揮、可回放。

---

# 1. 與既有電動商用車計畫銜接

本系統應銜接既有多用途電動商用車計畫。既有平台已朝「後車廂模組化」、「能源負載管理」、「智慧座艙」、「緊急供電」、「偏鄉行動超商」、「災區物資車」、「救災支援車」方向規劃。

本專案新增的「無人機矩陣航母車斗模組」應作為其中一種可抽換任務艙，讓同一台電動商用車可以依場景切換：

1. Service Mode：餐車 / 行動超商 / 活動支援。
2. Disaster Mode：救災 / 通訊中繼 / 夜間照明 / 災區巡查。
3. Counter-UAS Mode：低空空域監測 / 鳥機分類 / 未知目標追蹤。
4. Simulation Game Mode：反無人機戰術推演遊戲化展示。

建議預設車型：中華 ET35 電動商用車。

後車斗模組設計方向：

1. 可拆卸。
2. 可抽換。
3. 可標準化量產。
4. 可快速切換用途。
5. 可接車載電池、V2L、外接市電與太陽能補能。
6. 可作為多車隊分散式低空監控節點。

---

# 2. 重要安全邊界

本系統目前定位為 A 層能力：偵測、辨識、追蹤、態勢感知、韌性車隊、模擬推演、訓練展示、證據留存。

## 2.1 可以實作

1. 雷達掃描儀畫面。
2. 都卜勒雷達訊號分析。
3. Range-Doppler Map。
4. Micro-Doppler 特徵展示。
5. 鳥 / 無人機分類。
6. 低空目標追蹤。
7. 多感測融合。
8. 威脅分數。
9. 航跡預測。
10. 目標狀態向量估測。
11. 保護區 / 警戒區 / 禁航區展示。
12. 本方無人機派遣確認。
13. 無人機矩陣航母車斗管理。
14. 車隊韌性節點管理。
15. 戰術推演遊戲化畫面。
16. 虛擬鎖定動畫。
17. 虛擬攔截路徑視覺化。
18. 模擬命中 / 模擬失誤 / 目標逃逸 / 誤判更正等遊戲結果。
19. 事件回放。
20. PDF / JSON / CSV / 截圖報告匯出。

## 2.2 不可實作

不得實作任何可直接接到實體武器、干擾器、發射器或攻擊設備的控制流程，包括：

1. 真實武器導引參數輸出。
2. 真實發射控制指令。
3. 實體干擾器控制指令。
4. 擊落決策 API。
5. 自動攻擊決策流程。
6. 可直接串接實體武器模組的控制介面。
7. 可造成實體無人機失能、墜落、干擾或破壞的控制邏輯。

若需要展示戰鬥效果，請一律做成：

`Simulation Game Mode / No External Weapon Control / Training & Demonstration Only`

所有鎖定、攔截、命中、擊落效果都只能存在於螢幕、遊戲世界、模擬資料庫與回放報告中。

---

# 3. 系統總體架構

本系統分為 12 個主要模組：

1. Dashboard Command Center Module
2. Radar Excellence Module
3. Doppler Scientific Proof Module
4. Bird-UAV Classification Excellence Module
5. Multi-Sensor Fusion Module
6. Threat Reasoning Module
7. Counter-UAS Situation Awareness Module
8. Counter-UAS Combat Simulation Game Module
9. UAV Carrier Box Resilience Node Module
10. Vehicle Fleet Resilience Module
11. Evidence Chain and Replay Module
12. Presentation Mode Module

---

# 4. Dashboard Command Center Module

## 4.1 目標

首頁必須一打開就像低空空域指揮中心，不可像普通網頁儀表板。畫面要讓參觀者立即感受到這是一套反無人機韌性平台。

## 4.2 首頁資訊卡

必須顯示：

1. Active Radar Tracks
2. Classified UAVs
3. Classified Birds
4. Unknown Targets
5. High Threat Simulation Targets
6. Friendly UAVs Airborne
7. Carrier Box Ready Drones
8. Charging Drones
9. Vehicle Fleet Nodes
10. Current Mode
11. Active Protected Zone
12. Open Incidents

## 4.3 首頁三大視窗

中央主畫面建議三欄：

1. 左側：雷達小地圖。
2. 中央：目前選定目標的 Doppler / Classification 摘要。
3. 右側：無人機矩陣航母車斗與車隊狀態。

底部顯示事件時間軸與展示控制按鈕。

## 4.4 展示大按鈕

首頁必須有下列大按鈕：

1. 一鍵啟動完整展示。
2. 雷達掃描展示。
3. 鳥 / 無人機辨識展示。
4. 未知目標威脅推理展示。
5. 派出本方無人機確認。
6. 戰術推演遊戲模式。
7. 事件回放。
8. 匯出展示報告。
9. 重置展示資料。

---

# 5. Radar Excellence Module

## 5.1 目標

雷達頁面是第一視覺衝擊，必須做到像真正的低空空域監控中心。

## 5.2 必須功能

1. PPI 圓形雷達掃描。
2. 旋轉掃描線。
3. 掃描線餘暈效果。
4. 同心距離環。
5. 方位角刻度。
6. 北向指標。
7. 目標點動態閃爍。
8. 航跡尾線。
9. 多目標追蹤。
10. 目標 ID 標籤。
11. 高度顯示。
12. 速度顯示。
13. 航向顯示。
14. 分類顯示。
15. 保護區顯示。
16. 禁航區顯示。
17. 警戒區顯示。
18. 車隊防護圈顯示。
19. 目標點選後詳細資訊面板。
20. 歷史航跡回放。

## 5.3 目標分類顏色

1. Green：Friendly UAV
2. Blue：Recon UAV
3. Cyan：Relay UAV
4. Gray：Bird
5. Yellow：Unknown
6. Orange：Suspicious UAV
7. Red：High Threat Simulation
8. Purple：Multi-target / Swarm-like Pattern

## 5.4 目標資訊面板

點選目標後顯示：

1. Track ID
2. Classification
3. Range
4. Azimuth
5. Elevation
6. Altitude
7. Radial Velocity
8. Ground Speed
9. Heading
10. Signal Strength
11. Doppler Shift
12. Radar Confidence
13. Vision Confidence
14. Fusion Confidence
15. Threat Score
16. Time First Seen
17. Time Last Seen
18. Suggested Action

---

# 6. Doppler Scientific Proof Module

## 6.1 目標

這是本平台最核心的科學證據頁。大型無人機公司擅長飛行與展演，但本平台要展示雷達訊號理解能力。此頁必須像研究級平台。

## 6.2 必須頁籤

1. Range-Doppler Map
2. Micro-Doppler Signature
3. Spectrogram
4. Bird vs UAV Comparison
5. Signal Feature Table
6. Dataset Evidence
7. Model Confidence

## 6.3 必須顯示的訊號圖

1. Range-Doppler 熱圖。
2. Time-Frequency Spectrogram。
3. Micro-Doppler Pattern。
4. Target Echo Strength。
5. Radial Velocity Curve。
6. Signal-to-Noise Ratio。
7. Rotor Signature Score。
8. Wingbeat Score。

## 6.4 鳥與無人機差異展示

### Bird 顯示說明

1. 拍翅訊號較不穩定。
2. 航跡較自然飄動。
3. 速度變化較不規則。
4. Micro-Doppler 呈現生物運動特徵。

### UAV 顯示說明

1. 旋翼訊號較規律。
2. 可懸停。
3. 可直線前進。
4. 可突然折返。
5. 速度與高度控制較機械化。
6. Micro-Doppler 呈現旋翼週期特徵。

## 6.5 物理計算展示

請實作展示用計算：

1. Doppler Shift
2. Radial Velocity
3. Target Echo Strength
4. Signal-to-Noise Ratio
5. Micro-Doppler Pattern Score
6. Rotor Signature Score
7. Wingbeat Score
8. Time-Frequency Feature
9. Velocity Variance
10. Motion Regularity

---

# 7. Bird-UAV Classification Excellence Module

## 7.1 目標

分類頁不能只顯示「UAV 95%」，必須讓參觀者理解為什麼模型這樣判斷。

## 7.2 資料集接入

使用者已有 7 萬多筆實際雷達資料。請建立可插拔 Dataset Adapter，不可寫死 mock data。

若真實資料尚未接入，先用 sample-data 模擬，但必須保留真實資料接口。

## 7.3 資料格式

```json
{
  "track_id": "T-0001",
  "timestamp": "2026-07-02T10:00:00",
  "range_m": 230.5,
  "azimuth_deg": 135.2,
  "altitude_m": 82.1,
  "radial_velocity_mps": 7.3,
  "signal_strength": -42.8,
  "micro_doppler_features": [0.12, 0.38, 0.51],
  "spectrogram_ref": "sample_0001.npy",
  "label": "uav",
  "source": "radar_dataset"
}
```

## 7.4 分類類別

至少支援：

1. bird
2. uav
3. unknown
4. clutter
5. multi-target

## 7.5 模型架構

請建立可插拔模型架構：

```text
models/
├─ bird_uav_classifier.py
├─ feature_extractor.py
├─ inference_service.py
├─ model_registry.py
└─ adapters/
   ├─ sklearn_adapter.py
   ├─ pytorch_adapter.py
   └─ mock_adapter.py
```

## 7.6 Classification Result Card

每個目標顯示：

1. Track ID
2. Final Class
3. Bird Probability
4. UAV Probability
5. Unknown Probability
6. Radar Confidence
7. Vision Confidence
8. Fusion Confidence
9. Key Reason 1
10. Key Reason 2
11. Key Reason 3
12. Recommended Operator Review

## 7.7 XAI 解釋展示

顯示以下特徵對分類的貢獻：

1. Rotor Signature 對 UAV 判斷貢獻。
2. Wingbeat Score 對 Bird 判斷貢獻。
3. Motion Regularity 對 UAV 判斷貢獻。
4. Hover Probability 對 UAV 判斷貢獻。
5. Trajectory Noise 對 Bird 判斷貢獻。

## 7.8 資料集摘要

Classification 頁面顯示：

1. Total Samples
2. Bird Samples
3. UAV Samples
4. Unknown Samples
5. Training / Validation / Test Split
6. Accuracy
7. Precision
8. Recall
9. F1-score
10. Confusion Matrix
11. Feature Importance
12. Representative Samples
13. Similar Signal Top 5

---

# 8. Multi-Sensor Fusion Module

## 8.1 目標

單一雷達會被質疑，單一影像也會被質疑。本系統必須展示「雷達 + 影像 + 任務資料 + 車隊狀態」融合。

## 8.2 融合來源

1. Radar Track
2. Doppler Classification
3. Camera Detection
4. Vision Tracking
5. Friendly UAV Telemetry
6. Carrier Box Status
7. Protected Zone Definition
8. Operator Confirmation

## 8.3 Fusion State

每個目標有融合狀態：

1. Radar Only
2. Vision Only
3. Radar + Vision
4. Radar + Telemetry
5. Fusion Confirmed
6. Conflict Detected
7. Operator Review Required

## 8.4 Fusion UI

畫面分三欄：

1. 左欄：Radar Track
2. 中欄：Vision Detection
3. 右欄：Fusion Result

每一筆資料要有連線動畫，讓參觀者看得懂資料如何融合。

---

# 9. Threat Reasoning Module

## 9.1 目標

A 層不是攻擊，而是威脅理解。Threat Reasoning 要做得像指揮中心的大腦。

## 9.2 Threat Score 組成

Threat Score 僅作為態勢感知與訓練展示，不作為真實攻擊決策。

基礎分數：

1. Unknown Target：+15
2. Classified as UAV：+20
3. Fusion Confirmed UAV：+20
4. Entering Protected Zone：+25
5. Approaching Vehicle：+15
6. Low Altitude Approach：+10
7. High Speed Approach：+10
8. Hovering Near Asset：+15
9. Following Friendly UAV：+15
10. Swarm-like Pattern：+20
11. Signal Anomaly：+10

## 9.3 Threat Level

1. 0–20：Normal
2. 21–40：Observe
3. 41–60：Warning
4. 61–80：Critical
5. 81–100：Simulation Emergency

## 9.4 Suggested Response

只能做非武裝應變建議：

1. Continue Monitoring
2. Dispatch Recon UAV
3. Activate Camera Zoom
4. Record Evidence
5. Notify Operator
6. Trigger Safety Return
7. Mark Protected Zone
8. Switch to Disaster / Resilience Mode
9. Start Simulation Drill
10. Export Incident Report

不得出現真實攻擊控制建議。

---

# 10. Counter-UAS Situation Awareness Module

## 10.1 目標

建立反無人機態勢感知頁，讓展示重點從「無人機表演」拉回「低空空域韌性」。

## 10.2 必要功能

1. 空域總覽。
2. 鳥 / 無人機 / 未知目標分類。
3. 目標威脅分數。
4. 保護區設定。
5. 禁航區模擬。
6. 目標是否進入保護區。
7. 目標是否接近車隊。
8. 目標是否跟隨本方無人機。
9. 目標是否疑似干擾表演。
10. 目標是否疑似偵察。
11. 可派出 Recon UAV 做確認。
12. 可保存事件證據。

## 10.3 Suggested Response 面板

顯示：

1. Continue Monitoring
2. Dispatch Recon UAV
3. Notify Operator
4. Activate Warning Broadcast
5. Record Evidence
6. Trigger Safety Return
7. Switch to Emergency Mode
8. Contact Authorized Response Team

---

# 11. Counter-UAS Combat Simulation Game Module

## 11.1 目標

此模組是戰術推演遊戲與科學視覺化展示，不是實體武器控制系統。

此模組要做成最有震撼力的展示頁，但所有運算與結果只存在於遊戲世界與展示資料庫，不輸出任何可接真實武器、干擾器、發射器或外部攻擊設備的控制指令。

## 11.2 固定畫面標示

畫面左上角固定顯示：

```text
Simulation Game Mode
No External Weapon Control
Training / Demonstration Only
```

## 11.3 可實作功能

1. 遊戲化雷達畫面。
2. 目標進入空域。
3. 鳥類 / 無人機分類。
4. 目標威脅分數。
5. 遊戲化 Lock-on 動畫。
6. 虛擬攔截軌跡。
7. 虛擬防禦單元動畫。
8. 虛擬飛彈 / 虛擬雷射 / 虛擬攔截無人機效果。
9. 命中、失誤、逃逸、誤判為鳥類等遊戲結果。
10. 戰術分數與任務評分。
11. Replay 回放。
12. 教育訓練模式。

## 11.4 科學計算展示

請在遊戲效果背後加入可視化科學計算：

1. Doppler Shift 計算展示。
2. Radial Velocity 計算展示。
3. Micro-Doppler 特徵展示。
4. 目標狀態向量估測。
5. Kalman Filter 航跡平滑。
6. 預測航跡。
7. 最近接近點。
8. 目標進入保護區倒數。
9. 虛擬攔截時間。
10. 命中機率視覺化。

## 11.5 遊戲流程

1. 雷達掃描空域。
2. 目標出現在雷達畫面。
3. 系統根據都卜勒訊號分類為 Bird / UAV / Unknown。
4. Unknown UAV 進入保護區。
5. 系統顯示 Threat Score。
6. 玩家或展示人員按下「Engage Simulation」。
7. 顯示虛擬 Lock-on。
8. 顯示虛擬攔截路徑。
9. 顯示遊戲結果：
   - Simulated Hit
   - Simulated Miss
   - Target Evaded
   - Reclassified as Bird
10. 事件存入 Replay。

## 11.6 模擬結果

1. Simulated Hit
2. Simulated Miss
3. Target Evaded
4. Target Reclassified as Bird
5. Friendly UAV Confirmed Target
6. Protected Zone Breach Prevented
7. Operator Review Required

---

# 12. High-Fidelity Airspace Physics Simulation Module

## 12.1 目標

此模組展現高真實度空域物理推演能力。它不是武器控制，而是科學計算與螢幕展示。

## 12.2 允許實作內容

1. 目標狀態向量估測：
   - position_x
   - position_y
   - altitude
   - velocity_x
   - velocity_y
   - vertical_velocity
   - heading
   - acceleration

2. 雷達量測模擬：
   - range
   - azimuth
   - elevation
   - radial_velocity
   - signal_strength
   - doppler_shift
   - micro_doppler_signature

3. 航跡預測：
   - constant velocity prediction
   - constant acceleration prediction
   - Kalman filter tracking
   - uncertainty ellipse
   - predicted path visualization

4. 鳥 / 無人機辨識：
   - rotor signature score
   - wingbeat score
   - motion regularity
   - hover probability
   - trajectory smoothness
   - classification confidence

5. 虛擬攔截幾何展示：
   - predicted intercept zone
   - closest approach point
   - time-to-intercept visualization
   - virtual response path
   - no-fly zone boundary
   - protected asset boundary

## 12.3 Physics Simulation 頁面五區

1. 雷達態勢區：PPI、目標位置、航跡尾線、預測航跡、不確定性橢圓、保護區邊界。
2. 多普勒訊號區：Range-Doppler、Spectrogram、Micro-Doppler、Doppler Shift、Signal Strength。
3. 目標分類區：Bird Probability、UAV Probability、Unknown Probability、Rotor Signature Score、Wingbeat Score、Fusion Confidence。
4. 虛擬推演區：Predicted Path、Virtual Response Path、Closest Approach Point、Time to Protected Zone、Simulation Result。
5. 事件證據區：Event ID、Track ID、Radar Snapshot、Doppler Snapshot、Classification Result、Operator Notes、Export Report。

---

# 13. UAV Carrier Box Resilience Node Module

## 13.1 目標

無人機矩陣航母車斗不只是表演放飛，而是低空空域韌性節點。

## 13.2 建議命名

中文：無人機矩陣航母車斗模組

英文：UAV Matrix Carrier Box

模組頁名稱：Carrier Box

## 13.3 核心功能

1. 12 / 18 / 24 格矩陣式無人機艙位。
2. 每格顯示 Slot ID、Drone ID、Battery、Payload、Status、Temperature、Charging State。
3. 支援無人機狀態：
   - Docked
   - Charging
   - Ready
   - Airborne
   - Returning
   - Maintenance
   - Fault
4. 支援無人機類型：
   - Recon UAV
   - Relay UAV
   - Lighting UAV
   - Mapping UAV
   - Inspection UAV
   - Show UAV
5. 可派出 Recon UAV 確認未知目標。
6. 可派出 Relay UAV 做通訊中繼。
7. 可派出 Lighting UAV 做夜間照明。
8. 可派出 Mapping UAV 做災區建圖。
9. 可派出 Show UAV 做平時展示。
10. 支援自動回收與充電。
11. 支援任務輪替。
12. 支援多車協同。

## 13.4 建議艙位配置

1. 12 格展示型：3 × 2 × 2。
2. 18 格任務型：3 × 2 × 3。
3. 24 格高階型：4 × 2 × 3。

系統必須參數化，不可寫死一種配置。

## 13.5 能源狀態

頁面顯示：

1. 車載輔助電池 SOC。
2. 外接市電狀態。
3. V2L 狀態。
4. 太陽能補能功率。
5. 目前總充電功率。
6. 每格充電狀態。
7. 溫度 / 散熱 / 消防告警。

## 13.6 與 Counter-UAS 串接

當雷達發現 Unknown UAV：

1. 系統建議派出 Recon UAV。
2. Carrier Box 頁顯示 Ready Recon UAV。
3. 操作員按下 Dispatch Recon。
4. 本方無人機狀態變為 Airborne。
5. Fusion 頁接收本方無人機視覺資料。
6. Counter-UAS 頁更新 Threat Score。
7. Evidence 頁保存事件。

---

# 14. Vehicle Fleet Resilience Module

## 14.1 目標

單台車是產品，多台車是系統。必須展示多車協同，讓政府或國防相關單位看到可擴充性。

## 14.2 車隊角色

每台車可設定角色：

1. Radar Node
2. UAV Carrier Node
3. Power Supply Node
4. Command Node
5. Disaster Support Node
6. Communication Relay Node
7. Mobile Service Node

## 14.3 功能

1. 顯示多台車位置。
2. 顯示車隊覆蓋範圍。
3. 顯示低空監控網。
4. 顯示各車電量。
5. 顯示各車無人機數量。
6. 顯示任務分工。
7. 顯示各車目前模式。
8. 支援車隊事件回放。

## 14.4 多車展示劇本

1. 車 A 擔任雷達節點。
2. 車 B 擔任無人機航母節點。
3. 車 C 擔任供電與通訊節點。
4. Unknown UAV 進入空域。
5. 車 A 偵測。
6. 車 B 派出 Recon UAV。
7. 車 C 提供通訊中繼。
8. 系統完成分類、追蹤、證據留存。
9. 進入 Simulation Game Mode 做訓練推演。

---

# 15. Evidence Chain and Replay Module

## 15.1 目標

正式平台必須有證據鏈，不能只有即時畫面。

## 15.2 每個事件保存

1. Event ID
2. Time
3. Location
4. Radar Track
5. Doppler Snapshot
6. Spectrogram Snapshot
7. Vision Snapshot
8. Classification Result
9. Fusion Result
10. Threat Score
11. Suggested Response
12. Operator Action
13. Simulation Result
14. Replay File
15. Exported Report

## 15.3 匯出格式

1. PDF
2. JSON
3. CSV
4. Screenshot Bundle

## 15.4 PDF 報告內容

1. 封面
2. 事件摘要
3. 雷達截圖
4. 都卜勒訊號圖
5. 分類結果
6. 多感測融合結果
7. 威脅分級
8. 操作員處置
9. 推演結果
10. 結論

---

# 16. Presentation Mode Module

## 16.1 目標

明天展示時要能一鍵播放，不讓操作人員手忙腳亂。

## 16.2 頁面路徑

`/presentation`

## 16.3 功能

1. 一鍵播放完整展示流程。
2. 一鍵切換場景。
3. 一鍵重置資料。
4. 一鍵跳到雷達頁。
5. 一鍵跳到 Doppler 頁。
6. 一鍵跳到分類頁。
7. 一鍵跳到車斗頁。
8. 一鍵跳到戰術推演遊戲頁。
9. 一鍵匯出展示報告。
10. 一鍵進入英文 UI。

## 16.4 展示劇本

### Demo 1：我們看得見天空

展示雷達掃描，出現多個目標。

### Demo 2：我們分得出鳥和無人機

切到 Doppler 與 Classification，顯示鳥與無人機特徵差異。

### Demo 3：我們追得住未知目標

切到 Fusion 與 Counter-UAS，顯示 Unknown UAV 的航跡與威脅分數。

### Demo 4：我們可以派本方無人機確認

切到 Carrier Box，派出 Recon UAV。

### Demo 5：我們可以做戰術推演遊戲化展示

切到 Simulation Game Mode，顯示虛擬鎖定與虛擬攔截推演。

### Demo 6：我們可以留下證據

切到 Evidence，匯出事件報告。

### Demo 7：我們可以平轉韌性

切到 Vehicle Mode，展示 Service / Disaster / Counter-UAS / Simulation 四種模式。

---

# 17. 前端頁面

請建立以下頁面：

1. `/dashboard`
2. `/radar`
3. `/doppler`
4. `/classification`
5. `/fusion`
6. `/counter-uas`
7. `/physics-simulation`
8. `/simulation-game`
9. `/carrier-box`
10. `/vehicle-fleet`
11. `/vehicle-mode`
12. `/evidence`
13. `/playback`
14. `/presentation`
15. `/settings`

---

# 18. 後端 API

## 18.1 Radar API

1. `GET /api/radar/live`
2. `GET /api/radar/tracks`
3. `GET /api/radar/track/{id}`
4. `GET /api/radar/ppi`
5. `GET /api/radar/range-doppler/{id}`
6. `GET /api/radar/spectrogram/{id}`
7. `GET /api/radar/micro-doppler/{id}`

## 18.2 Classification API

1. `POST /api/classification/infer`
2. `GET /api/classification/result/{track_id}`
3. `GET /api/classification/dataset-summary`
4. `GET /api/classification/confusion-matrix`
5. `GET /api/classification/feature-importance`
6. `GET /api/classification/similar-samples/{track_id}`

## 18.3 Fusion API

1. `GET /api/fusion/tracks`
2. `GET /api/fusion/track/{id}`
3. `POST /api/fusion/manual-confirm`
4. `POST /api/fusion/calibrate`

## 18.4 Threat API

1. `GET /api/threats`
2. `POST /api/threats/evaluate`
3. `GET /api/threats/{track_id}`
4. `POST /api/threats/protected-zone`

## 18.5 Carrier Box API

1. `GET /api/carrier-box/matrix`
2. `GET /api/carrier-box/slots`
3. `POST /api/carrier-box/dispatch-recon`
4. `POST /api/carrier-box/return-drone`
5. `POST /api/carrier-box/charge-drone`
6. `POST /api/carrier-box/switch-layout`

## 18.6 Vehicle Fleet API

1. `GET /api/fleet/vehicles`
2. `GET /api/fleet/coverage`
3. `POST /api/fleet/assign-role`
4. `POST /api/fleet/switch-mode`

## 18.7 Simulation Game API

1. `POST /api/simulation-game/start`
2. `POST /api/simulation-game/engage`
3. `GET /api/simulation-game/state`
4. `GET /api/simulation-game/result/{event_id}`
5. `POST /api/simulation-game/reset`

## 18.8 Physics Simulation API

1. `POST /api/physics/predict-track`
2. `GET /api/physics/state-vector/{track_id}`
3. `GET /api/physics/closest-approach/{track_id}`
4. `GET /api/physics/uncertainty/{track_id}`
5. `GET /api/physics/virtual-response-path/{track_id}`

## 18.9 Evidence API

1. `GET /api/evidence/events`
2. `GET /api/evidence/events/{id}`
3. `POST /api/evidence/archive`
4. `POST /api/evidence/export-pdf`
5. `POST /api/evidence/export-json`
6. `POST /api/evidence/export-csv`
7. `POST /api/evidence/export-bundle`

## 18.10 Presentation API

1. `GET /api/presentation/scripts`
2. `POST /api/presentation/play/{script_id}`
3. `POST /api/presentation/next`
4. `POST /api/presentation/reset`
5. `POST /api/presentation/export-report`

---

# 19. 技術架構

## 19.1 Frontend

1. React 或 Next.js
2. TypeScript
3. Tailwind CSS
4. Canvas / WebGL
5. ECharts
6. WebSocket
7. Zustand 或 Redux
8. Konva 或 Fabric.js 用於編隊與態勢圖

## 19.2 Backend

1. Python FastAPI
2. PostgreSQL
3. Redis
4. MinIO
5. WebSocket
6. APScheduler 或 Celery

## 19.3 AI / Signal Services

1. Python
2. NumPy
3. SciPy
4. PyTorch 或 scikit-learn adapter
5. OpenCV
6. YOLO adapter
7. ByteTrack / DeepSORT adapter
8. 自訂 Doppler feature extractor

## 19.4 Docker Compose 服務

必須提供：

1. frontend
2. backend
3. radar-sim
4. doppler-analyzer
5. classifier
6. vision-fusion
7. simulation-engine
8. playback-engine
9. postgres
10. redis
11. minio
12. nginx

---

# 20. 專案目錄結構

```text
counter-uas-radar-carrier/
├─ docker-compose.yml
├─ .env.example
├─ README.md
├─ docs/
│  ├─ architecture.md
│  ├─ demo-script.md
│  ├─ safety-boundary.md
│  ├─ radar-doppler-design.md
│  ├─ classification-design.md
│  ├─ counter-uas-mode.md
│  ├─ simulation-game-mode.md
│  ├─ carrier-box-design.md
│  ├─ evidence-report.md
│  └─ presentation-flow.md
├─ frontend/
│  ├─ app/
│  │  ├─ dashboard/
│  │  ├─ radar/
│  │  ├─ doppler/
│  │  ├─ classification/
│  │  ├─ fusion/
│  │  ├─ counter-uas/
│  │  ├─ physics-simulation/
│  │  ├─ simulation-game/
│  │  ├─ carrier-box/
│  │  ├─ vehicle-fleet/
│  │  ├─ vehicle-mode/
│  │  ├─ evidence/
│  │  ├─ playback/
│  │  ├─ presentation/
│  │  └─ settings/
│  ├─ components/
│  │  ├─ radar/
│  │  ├─ doppler/
│  │  ├─ classification/
│  │  ├─ fusion/
│  │  ├─ threat/
│  │  ├─ carrier/
│  │  ├─ fleet/
│  │  ├─ simulation/
│  │  ├─ evidence/
│  │  └─ layout/
│  ├─ lib/
│  ├─ store/
│  └─ public/
├─ backend/
│  ├─ app/
│  │  ├─ api/
│  │  ├─ core/
│  │  ├─ models/
│  │  ├─ schemas/
│  │  ├─ services/
│  │  ├─ websocket/
│  │  └─ utils/
│  └─ tests/
├─ services/
│  ├─ radar-sim/
│  ├─ doppler-analyzer/
│  ├─ classifier/
│  ├─ vision-fusion/
│  ├─ simulation-engine/
│  └─ playback-engine/
├─ sample-data/
│  ├─ radar_tracks.json
│  ├─ bird_samples.json
│  ├─ uav_samples.json
│  ├─ carrier_box.json
│  ├─ vehicles.json
│  ├─ fleet.json
│  ├─ demo_events.json
│  └─ presentation_scripts.json
└─ scripts/
   ├─ init-demo-data.sh
   ├─ run-presentation-demo.sh
   ├─ reset-demo.sh
   └─ health-check.sh
```

---

# 21. 資料模型

## 21.1 Vehicle

1. id
2. name
3. role
4. mode
5. location
6. battery_soc
7. auxiliary_battery_soc
8. solar_input_watt
9. carrier_module_attached
10. total_slots
11. occupied_slots
12. network_status

## 21.2 Drone

1. id
2. vehicle_id
3. slot_id
4. type
5. payload_type
6. battery_soc
7. health_status
8. state
9. current_mission_id
10. last_launch_time
11. last_return_time
12. telemetry_status

## 21.3 Slot

1. id
2. vehicle_id
3. slot_code
4. status
5. charging
6. temperature
7. drone_id
8. fault_code

## 21.4 RadarTrack

1. id
2. timestamp
3. range_m
4. azimuth_deg
5. elevation_deg
6. altitude_m
7. radial_velocity_mps
8. ground_speed_mps
9. heading_deg
10. signal_strength
11. doppler_shift
12. classification
13. confidence

## 21.5 ClassificationResult

1. id
2. track_id
3. final_class
4. bird_probability
5. uav_probability
6. unknown_probability
7. radar_confidence
8. vision_confidence
9. fusion_confidence
10. key_reasons
11. feature_contributions

## 21.6 ThreatEvent

1. id
2. track_id
3. threat_score
4. threat_level
5. protected_zone_id
6. suggested_response
7. operator_action
8. simulation_result
9. archived

## 21.7 EvidenceEvent

1. id
2. event_time
3. radar_snapshot_ref
4. doppler_snapshot_ref
5. spectrogram_snapshot_ref
6. vision_snapshot_ref
7. classification_result_ref
8. fusion_result_ref
9. threat_score
10. operator_notes
11. replay_ref
12. report_ref

---

# 22. UI 品質要求

所有畫面必須達到高階展示品質：

1. 深色科技風。
2. 雷達綠、科技藍、警示橘、威脅紅。
3. 字體大，投影清楚。
4. 卡片資訊不要太擠。
5. 圖表有動畫。
6. 雷達畫面要流暢。
7. Doppler 圖要像研究平台。
8. Simulation Game 頁要震撼。
9. Evidence 頁要像正式系統。
10. Presentation 頁要像產品發表會。
11. 每個重要頁面都要支援英文 UI。
12. 展示畫面不可出現亂碼或過小文字。

---

# 23. 明天展示口徑

## 23.1 主要說法

> 本平台不是一般無人機展演系統，而是把雷達掃描、都卜勒訊號分析、鳥與無人機分類、視覺辨識融合、無人機車斗部署與韌性車隊任務整合在一起。

> 無人機矩陣航母車斗不是單純放飛無人機，而是韌性車的任務模組。平時可以做救災、巡檢、餐車、活動支援；必要時可切換為 Counter-UAS 模式，用於低空空域監控、未知目標辨識、風險分級與應變推演。

> Simulation Game Mode 是螢幕上的戰術推演展示，不串接任何實體武器、干擾器或發射設備。它展示的是雷達、AI、物理模型、目標追蹤與指揮介面的科學能力。

## 23.2 對無人機公司說法

> 你們是無人機飛行與展演的專家，我們不是要重做你們已經很強的部分。我們做的是低空空域的雷達辨識、鳥機分類、態勢感知、韌性車隊、事件回放與戰術推演遊戲化介面。雙方結合後，可以形成完整的低空經濟與韌性展示方案。

## 23.3 對政府韌性計畫說法

> 這是一套平轉韌性的電動商用車應用。平時是餐車、物流、活動服務、巡檢與救災支援；必要時換掛無人機矩陣航母車斗模組，成為低空空域監測與韌性指揮節點。

---

# 24. 驗收標準

完成後必須達成：

1. Docker Compose 可一鍵啟動。
2. Dashboard 可呈現指揮中心感。
3. Radar 頁可顯示動態雷達掃描與多目標航跡。
4. Doppler 頁可顯示 Range-Doppler、Spectrogram、Micro-Doppler。
5. Classification 頁可展示鳥 / 無人機分類結果與理由。
6. Fusion 頁可展示 Radar / Vision / Telemetry 融合。
7. Counter-UAS 頁可展示威脅分級與應變建議。
8. Physics Simulation 頁可展示航跡預測與高真實度物理推演。
9. Simulation Game 頁可展示遊戲化虛擬鎖定與虛擬攔截效果。
10. Carrier Box 頁可展示 12 / 18 / 24 格無人機矩陣航母車斗。
11. Vehicle Fleet 頁可展示多車韌性節點。
12. Evidence 頁可保存事件並匯出報告。
13. Presentation 頁可一鍵播放明天展示劇本。
14. 所有 Simulation Game 功能皆不得輸出外部控制訊號。
15. README、API 文件、demo script、測試文件必須完整。

---

# 25. 測試需求

## 25.1 單元測試

1. Radar Track 更新。
2. Doppler feature extraction。
3. Classification inference。
4. Fusion state calculation。
5. Threat Score calculation。
6. Carrier Box 狀態轉換。
7. Simulation Game 狀態轉換。
8. Evidence archive。
9. PDF export。

## 25.2 整合測試

1. 前後端 API 串接。
2. WebSocket 即時資料推播。
3. Radar → Classification → Fusion → Threat 流程。
4. Threat → Dispatch Recon UAV → Evidence 流程。
5. Presentation Mode 一鍵播放流程。

## 25.3 展示測試

1. 一鍵啟動展示。
2. 雷達掃描展示。
3. 鳥 / 無人機辨識展示。
4. 未知目標威脅推理展示。
5. 無人機矩陣航母車斗展示。
6. 戰術推演遊戲展示。
7. 事件報告匯出。
8. 系統重置。

---

# 26. Claude Code 執行指令

請 Claude Code 依照本文件完整建立專案，不要只做靜態頁，不要只做假畫面。請完成可展示的 A 層超級完美版系統。

必須完成：

1. 建立完整專案目錄。
2. 建立 Docker Compose。
3. 建立前端所有頁面。
4. 建立 FastAPI 後端。
5. 建立 WebSocket 即時資料推播。
6. 建立雷達模擬資料流。
7. 建立 Doppler 訊號視覺化服務。
8. 建立鳥 / 無人機分類展示服務。
9. 建立多感測融合展示。
10. 建立 Threat Score。
11. 建立 Counter-UAS 態勢感知頁。
12. 建立高真實度物理推演頁。
13. 建立 Simulation Game Mode。
14. 建立 Carrier Box 狀態管理。
15. 建立 Vehicle Fleet 韌性車隊頁。
16. 建立 Evidence Export。
17. 建立 Presentation Mode。
18. 建立 sample data。
19. 建立 demo scripts。
20. 建立測試。
21. 建立 README 與 docs。
22. 完成後自動執行測試與修正。
23. 使用 `/loop` 持續完成到可展示狀態，不要中途停止詢問。

若真實雷達、真實 7 萬筆資料、真實攝影機、真實無人機尚未接入，請先使用 mock adapter 與 sample-data，但所有服務必須保留未來接入真實資料、真實雷達、真實影像串流、真實無人機 telemetry 的接口。

所有戰術推演、虛擬鎖定、虛擬攔截、命中、失誤、擊落效果皆限定為 Simulation Game Mode 的螢幕展示效果，不得建立任何外部武器控制或攻擊設備控制接口。

---

# 27. 最終交付物

Claude Code 最終需交付：

1. 可執行原始碼。
2. Docker Compose。
3. README.md。
4. API 文件。
5. UI 操作說明。
6. Demo Script 文件。
7. Safety Boundary 文件。
8. 測試結果。
9. 展示截圖。
10. Presentation Mode。
11. Evidence Report 範本。
12. 未來接真實雷達資料的 Adapter 說明。
13. 未來接 7 萬筆資料集的 Dataset Adapter 說明。
14. 未來接真實無人機 telemetry 的接口說明。

---

# 28. 最重要的成果判斷

完成後，參觀者要能清楚感受到：

1. 這不是一般無人機表演平台。
2. 這是一套低空空域反無人機韌性平台。
3. 我們具備雷達訊號理解能力。
4. 我們具備鳥 / 無人機分類能力。
5. 我們具備多感測融合能力。
6. 我們具備車載無人機矩陣部署能力。
7. 我們具備平轉韌性場景整合能力。
8. 我們具備戰術推演遊戲化展示能力。
9. 我們具備事件證據保存與回放能力。
10. A 層已經做到足夠完整，未來才有機會被信任進一步討論更高階合作。


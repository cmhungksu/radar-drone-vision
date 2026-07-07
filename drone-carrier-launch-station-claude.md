# Drone Show Studio Add-on：固定點車載航母啟動方案（Claude Code 實作規格）

> 專案定位：本文件是 `drone-show-studio` 的第二階段追加模組，目標是建立「固定點電動車載無人機航母／行動式 Drone-in-a-box 展演站」的動畫、排程、充電、艙位管理、起降模擬、故障節點回放與人力降低工具。
>
> 安全界線：本專案只產生 `SIMULATION_ONLY` 的動畫、排程、檢查報表與人機協作流程，不得產生可直接控制實機的飛控指令、mission upload、arming、takeoff、landing、setpoint、offboard command、MAVLink 寫入或任何可部署到實機的控制檔。

---

## 1. 產品概念

傳統大型無人機展演需要在地面鋪設大量起飛點，每台無人機都要依照編號放在廣場或空地上，會造成：

1. 場地需求很大。
2. 工作人員布署時間長。
3. 電池檢查、編號核對、位置校準容易出錯。
4. 下雨、潮濕、觀眾接近、地面不平整都會增加風險。
5. 每一次展演都像一次大型施工。

本方案改成「固定點車載航母啟動」。無人機平常收納在改裝電動車或拖車式車載艙內，展演時由同一個車載站分批起飛，到空中後依照排程進入第一張圖定位點。展演結束後再分批返回車載艙，進入充電、健康檢查、資料同步與下一輪待命。

這個特色不是為了讓所有無人機同秒起飛，而是用「分批起飛 + 空中等待區 + 到位時間差補償 + 軌跡動畫排程」取代大片地面陣列。

---

## 2. 核心目標

### 2.1 最大目標：降低播放工作人員人數

系統要用軟體與流程降低以下人力：

- 地面鋪點人員。
- 無人機逐台搬運人員。
- 電池逐台檢查人員。
- 編號核對人員。
- 場地安全巡檢人員。
- 展演後回收與充電人員。

注意：系統不得宣稱「完全無人值守」。實際商業展演仍需要合格操作人員、現場安全主管、空域申請、風險管理與保險。軟體目標是把大量重複性工作轉成自動化檢查、排程、動畫預演與報表。

### 2.2 產品差異化

本模組要在前端與影片中呈現以下特色：

- 電動車或拖車式無人機航母。
- 多艙位收納與充電。
- 車頂或側邊艙門開啟動畫。
- 無人機依序升降台推出。
- 起飛時 LED 關閉，避免未就位前畫面雜亂。
- 第一張圖就定位時，LED 進入藍色或指定定位色。
- 展演中依序切換 RGB LED。
- 失效節點由備援節點接替，只做模擬與動畫，不做實機控制。
- 展演後分批返回車載艙充電。
- 低電量、無法返航、艙位堵塞、充電失敗都可在動畫中重播。

---

## 3. 系統邊界與安全限制

### 3.1 嚴禁項目

Claude Code 不得建立下列功能：

- 可直接連線真實飛控的控制 API。
- 可上傳真實 mission 的檔案格式。
- MAVLink、PX4、ArduPilot、DJI SDK 等實機控制寫入。
- ARM / DISARM / TAKEOFF / LAND / RTL / SET_POSITION / SET_VELOCITY / OFFBOARD 等控制命令。
- GPS/IMU 失效時的真實飛行替補指令。
- 自動接管真機或自動改寫真機任務。
- 可繞過人工審核的「一鍵飛行」。

### 3.2 允許項目

Claude Code 可以建立：

- 車載航母 3D 模型。
- 艙位、充電、起降排程模擬。
- Blender 動畫輸出。
- Isaac Sim / Gazebo / WebGL 類數位孿生預覽接口。
- 失效節點與替補節點動畫。
- 飛行紀錄反推動畫，但只能輸出 `SIMULATION_ONLY`。
- 電力耗損與充電回補模擬。
- 場地 Canvas 禁入區、氣球、建築物、高空障礙物避讓動畫。
- 報表與人工審核流程。
- 未來 Real Flight Gateway 的介面保留，但實作為 disabled stub。

---

## 4. 技術定位：CadQuery、Blender、Isaac Sim 的分工

### 4.1 CadQuery

CadQuery 用於「可參數化的硬體與場域 CAD 模型」，不是主動畫引擎。

用途：

- 電動車外型簡化模型。
- 車頂艙門。
- 多層抽屜式無人機艙位。
- 升降平台。
- 充電接點示意。
- 維修抽屜。
- 風雨防護罩。
- 高空建築物與障礙物的簡化體積。
- 大型氣球的安全包絡外框。

輸出：

- STEP / STL / GLB 中繼模型。
- 提供 Blender 匯入使用。
- 不在 CadQuery 裡做路徑最佳化，不在 CadQuery 裡做 LED 動畫。

### 4.2 Blender

Blender 是主動畫引擎。

用途：

- 車載航母展開動畫。
- 無人機分批起飛。
- 空中等待區。
- 第一張圖定位。
- LED 顏色切換。
- 貝茲曲線軌跡。
- 回收與充電動畫。
- 失效節點重播。
- 客戶簡報 MP4 / WebM / GLB / .blend 輸出。

### 4.3 Isaac Sim

Isaac Sim 是第二階段高擬真驗證層，不是每次預覽都必跑。

用途：

- 高風險片段驗證。
- 艙口附近碰撞檢查。
- 起飛窗口擁塞檢查。
- 降落返回排隊檢查。
- 感測器視角模擬。
- 故障節點失聯後的動畫重播驗證。

不得用 Isaac Sim 產生真實控制命令。

---

## 5. 重要概念：固定點起飛，不等於同時起飛

車載航母的最大限制是起飛口數量有限，因此系統必須把傳統「全部地面展開」改成「分批出艙」模式。

### 5.1 基本流程

```text
車輛抵達固定點
→ 水平校正與場地檢查
→ 艙門開啟動畫
→ 第 1 批無人機推出
→ 起飛 LED 關閉
→ 進入空中等待區
→ 第 2 批無人機推出
→ 重複直到全部到位
→ 第一張圖定位完成
→ LED 開啟並進入展演
→ 展演完成
→ 分批返回等待區
→ 分批降落入艙
→ 充電 / 健康檢查 / 資料同步
→ 下一輪待命
```

### 5.2 空中等待區

因為同時起飛數量有限，必須建立「空中等待區」。等待區不得影響主畫面，也不能靠近障礙物。

等待區設計：

- 位於主展演圖形外側。
- 有高度層分區。
- 有批次編號。
- 有最大停留時間。
- 有最小距離限制。
- 有低電量退出規則。
- 可在 Blender 中以半透明圓環或格線顯示。

### 5.3 到位時間差補償

每一台無人機不必同時起飛，但必須在第一張圖亮燈前到位。

系統要計算：

- 艙位推出順序。
- 起飛批次。
- 起飛到等待區時間。
- 等待區到第一張圖定位點時間。
- 早到等待時間。
- 晚到風險。
- 電力損耗。
- 最小距離衝突。
- 障礙物繞行成本。

注意：此處只做模擬排程，不輸出真實飛控命令。

---

## 6. 資料模型

請 Claude Code 建立以下資料格式。

### 6.1 carrier_config.json

```json
{
  "schema": "carrier_config.v1",
  "mode": "SIMULATION_ONLY",
  "carrier": {
    "name": "EV Drone Carrier A",
    "type": "parked_vehicle_dock",
    "vehicle_length_m": 6.2,
    "vehicle_width_m": 2.1,
    "vehicle_height_m": 2.4,
    "dock_position_world": [0, 0, 0],
    "max_simultaneous_launch_slots": 4,
    "max_simultaneous_recovery_slots": 2,
    "bay_count": 60,
    "charging_ports": 60,
    "has_lift_platform": true,
    "has_weather_cover": true,
    "has_operator_console": true
  },
  "safety": {
    "parked_only": true,
    "real_flight_export_enabled": false,
    "minimum_operator_count_required": 2,
    "require_manual_review": true
  }
}
```

### 6.2 drone_bay_inventory.json

```json
{
  "schema": "drone_bay_inventory.v1",
  "mode": "SIMULATION_ONLY",
  "drones": [
    {
      "drone_id": "D001",
      "bay_id": "BAY-01",
      "battery_percent": 98,
      "health": "ready",
      "led_health": "ready",
      "gps_health": "sim_ready",
      "imu_health": "sim_ready",
      "assigned_role": "primary"
    },
    {
      "drone_id": "D061",
      "bay_id": "BAY-61",
      "battery_percent": 100,
      "health": "ready",
      "assigned_role": "reserve"
    }
  ]
}
```

### 6.3 launch_schedule.json

```json
{
  "schema": "launch_schedule.v1",
  "mode": "SIMULATION_ONLY",
  "show_id": "demo-carrier-show-001",
  "launch_plan": [
    {
      "wave": 1,
      "time_offset_sec": 0,
      "slot_id": "L1",
      "drone_id": "D001",
      "bay_id": "BAY-01",
      "led_state_during_ascent": "off",
      "target_wait_zone": "WZ-A-01",
      "first_formation_point": "P001"
    },
    {
      "wave": 1,
      "time_offset_sec": 0,
      "slot_id": "L2",
      "drone_id": "D002",
      "bay_id": "BAY-02",
      "led_state_during_ascent": "off",
      "target_wait_zone": "WZ-A-02",
      "first_formation_point": "P002"
    }
  ]
}
```

### 6.4 recovery_schedule.json

```json
{
  "schema": "recovery_schedule.v1",
  "mode": "SIMULATION_ONLY",
  "recovery_plan": [
    {
      "wave": 1,
      "time_offset_sec": 0,
      "recovery_slot_id": "R1",
      "drone_id": "D001",
      "target_bay_id": "BAY-01",
      "post_recovery_action": "charge_and_log"
    }
  ]
}
```

### 6.5 carrier_risk_report.json

```json
{
  "schema": "carrier_risk_report.v1",
  "mode": "SIMULATION_ONLY",
  "summary": {
    "total_drones": 60,
    "primary_drones": 50,
    "reserve_drones": 10,
    "estimated_launch_duration_sec": 180,
    "estimated_recovery_duration_sec": 240,
    "minimum_battery_after_show_percent": 38,
    "operator_reduction_score": 0.72
  },
  "warnings": [
    {
      "level": "medium",
      "type": "launch_queue_congestion",
      "message": "Wave 8 has too many drones waiting near WZ-A. Increase waiting zone spacing."
    }
  ]
}
```

---

## 7. 介面功能

### 7.1 Carrier Dashboard

建立車載航母儀表板，只顯示安全預覽與狀態，不顯示核心演算法。

頁面區塊：

- 車輛 / 拖車模型預覽。
- 艙位矩陣。
- 每台無人機狀態。
- 電量熱圖。
- 起飛波次表。
- 回收波次表。
- 等待區佔用率。
- 故障節點清單。
- 備援節點清單。
- 展演是否可進入人工審核。

### 7.2 Canvas 場域編輯器

使用者可以在場域上畫出：

- 車載航母位置。
- 觀眾區。
- 禁飛區。
- 高空建築物。
- 大型氣球。
- 臨時吊車。
- 燈塔、天線、舞台桁架。
- 主展演畫面區。
- 空中等待區。
- 回收進場區。

只要 Canvas 上某區塊被標記為障礙物或禁入區，後端模擬必須避開。前端不得自己計算路徑，只能送出障礙物幾何資料到後端。

### 7.3 航母動畫生成器

Blender 需要產生以下動畫：

- 車輛抵達固定點。
- 停車腳架放下。
- 車頂艙門開啟。
- 升降平台上升。
- 無人機分批推出。
- 起飛時 LED 關閉。
- 無人機到空中等待區。
- 第一張圖定位時 LED 亮藍色。
- 展演正式開始。
- 故障節點灰化。
- 備援節點從等待區補上。
- 展演結束後分批返回。
- 入艙後充電燈號亮起。
- 儀表板顯示下一輪可用電量。

---

## 8. 人力降低設計

### 8.1 原本人力流程

```text
搬運箱子
→ 打開箱子
→ 對照編號
→ 放到地面指定點
→ 檢查電池
→ 檢查螺旋槳
→ 檢查 LED
→ 檢查 GPS/IMU
→ 展演
→ 人工找回每台無人機
→ 拔電池或接充電
→ 收納
```

### 8.2 車載航母流程

```text
車輛定位
→ 系統掃描艙位
→ 系統產生起飛波次
→ 人員審核報表
→ 分批起飛動畫預演
→ 展演
→ 分批回收動畫預演
→ 入艙充電
→ 異常節點自動標記
```

### 8.3 軟體要量化人力降低

Dashboard 要計算：

- 預估布署時間。
- 預估回收時間。
- 預估需要工作人員數量。
- 與傳統地面鋪點方式相比節省比例。
- 每台無人機平均人工接觸次數。
- 每輪展演可重複播放次數。
- 低電量節點造成的等待成本。

---

## 9. 起飛與回收模擬策略

### 9.1 起飛波次

參數：

- `max_simultaneous_launch_slots`：同時可出艙數量。
- `launch_interval_sec`：每批間隔秒數。
- `safe_vertical_separation_m`：起飛高度層距。
- `wait_zone_capacity`：等待區容量。
- `first_frame_deadline_sec`：第一張圖亮燈期限。

輸出：

- 起飛波次動畫。
- 到位時間甘特圖。
- 風險警告。

### 9.2 回收波次

回收比起飛更難，因為低電量、風場、返航擁塞都會造成風險。模擬要呈現：

- 先回收低電量節點。
- 再回收主圖形邊緣節點。
- 最後回收核心節點。
- 每一批進入回收等待區。
- 回收口堵塞時，無人機在等待區排隊。
- 低電量節點若無法回到車載艙，只在模擬中標記為 emergency hold，不輸出實機處置命令。

---

## 10. LED 策略

### 10.1 起飛階段

起飛階段 LED 預設關閉：

```text
TAKEOFF_ASCENT：LED OFF
WAIT_ZONE_HOLD：LED OFF 或低亮度識別色
FIRST_FORMATION_LOCK：LED BLUE
SHOW_ACTIVE：依展演資料播放 RGB
RECOVERY：LED OFF 或安全識別色
DOCKED_CHARGING：艙位狀態燈顯示充電狀態
```

### 10.2 RGB 顏色資料

系統內部可用 16-bit RGB565 或 24-bit RGB888 建模，但前端只顯示色彩結果，不暴露色彩壓縮或編碼策略。

需要支援：

- 全白。
- 單色。
- 漸層。
- 閃爍。
- 呼吸燈。
- 同步變色。
- 故障節點灰色。
- 備援節點綠色接管動畫。
- 電量不足節點紅色警告動畫。

---

## 11. 故障與補位動畫

### 11.1 故障情境

模擬以下失效情境：

- 電池不足。
- LED 失效。
- GPS 漂移。
- IMU 異常。
- 通訊延遲。
- 無法準時到第一張圖定位。
- 艙位充電失敗。
- 回收口堵塞。
- 無人機無法返回原艙位。
- 高空氣球臨時進入安全包絡。
- 建築物或吊車臨時加入禁入區。

### 11.2 補位策略，只做動畫

補位策略以 `SIMULATION_ONLY` 呈現：

```text
故障節點灰化
→ 顯示故障原因
→ 備援節點從等待區移動到替補點
→ 原圖形微調
→ 產生前後比較動畫
→ 報表標記風險降低程度
```

不得輸出實機補位指令。

### 11.3 問題節點重播

系統需要一個「問題節點播放器」。可不斷播放某個節點從正常、耗電、偏移、失聯、替補、回收失敗的完整過程。

功能：

- 依 drone_id 選擇。
- 顯示電量曲線。
- 顯示位置偏移曲線。
- 顯示 LED 狀態。
- 顯示通訊狀態。
- 顯示是否由備援節點接替。
- 可匯出短影片給客戶或內部檢討。

---

## 12. 後端核心保護：避免被抄襲

所有重要邏輯都必須放後端：

- 艙位排程。
- 起飛波次排序。
- 回收波次排序。
- 電量預估。
- 等待區分配。
- 失效節點判斷。
- 備援節點選擇。
- 障礙物避讓。
- 第一張圖到位時間補償。
- 貝茲曲線控制點生成。
- IP 圖轉點位。
- 點位密度控制。
- 圖形細節取捨。

前端只拿：

- 降階後的動畫預覽資料。
- 不可逆推核心演算法的快取結果。
- 報表摘要。
- 影片輸出。
- 人工審核按鈕。

不得讓前端下載：

- 完整點位演算法。
- 完整權重。
- 完整最佳化成本函數。
- 可還原核心策略的中間資料。
- 實機控制資料。

---

## 13. 專案目錄建議

追加模組目錄名稱：

```text
drone-carrier-station
```

建議整體目錄：

```text
drone-show-studio/
├─ backend/
│  ├─ api/
│  ├─ private_core/
│  ├─ simulation/
│  ├─ carrier_station/
│  ├─ risk_report/
│  └─ disabled_real_flight_gateway/
├─ frontend/
│  ├─ canvas_editor/
│  ├─ carrier_dashboard/
│  ├─ animation_review/
│  └─ problem_replay/
├─ blender_pipeline/
│  ├─ scene_builder.py
│  ├─ carrier_model_importer.py
│  ├─ launch_wave_animator.py
│  ├─ recovery_wave_animator.py
│  ├─ led_animator.py
│  └─ render_exporter.py
├─ cadquery_models/
│  ├─ ev_carrier.py
│  ├─ dock_bay.py
│  ├─ lift_platform.py
│  ├─ charging_contact.py
│  └─ obstacle_proxy.py
├─ data_examples/
│  ├─ carrier_config.json
│  ├─ drone_bay_inventory.json
│  ├─ launch_schedule.json
│  ├─ recovery_schedule.json
│  └─ carrier_risk_report.json
├─ docs/
│  ├─ PRODUCT_CONCEPT.md
│  ├─ SAFETY_BOUNDARY.md
│  ├─ SECURITY_REVIEW.md
│  ├─ CARRIER_OPERATION_SIMULATION.md
│  └─ HUMAN_REDUCTION_REPORT.md
└─ tests/
   ├─ test_no_real_flight_export.py
   ├─ test_carrier_schedule.py
   ├─ test_launch_wave_conflict.py
   ├─ test_recovery_queue.py
   ├─ test_battery_turnaround.py
   └─ test_frontend_no_private_algorithm.py
```

---

## 14. Claude Code 實作任務

### 14.1 第一階段：資料模型與後端模擬

請完成：

1. 建立 `carrier_station` 模組。
2. 建立 JSON schema。
3. 建立艙位 inventory。
4. 建立起飛波次模擬器。
5. 建立回收波次模擬器。
6. 建立電量消耗與充電回補模型。
7. 建立等待區容量檢查。
8. 建立風險報表。
9. 所有輸出標記 `SIMULATION_ONLY`。
10. 建立測試確認無實機控制輸出。

### 14.2 第二階段：CadQuery 模型

請完成：

1. EV 車載航母簡化模型。
2. 車頂艙門。
3. 多層艙位。
4. 升降平台。
5. 充電接點示意。
6. 維修抽屜。
7. 障礙物 proxy 模型。
8. 匯出 Blender 可讀格式。

### 14.3 第三階段：Blender 動畫

請完成：

1. 車輛固定點場景。
2. 艙門開啟動畫。
3. 無人機推出動畫。
4. 分批起飛動畫。
5. 空中等待區動畫。
6. 第一張圖定位動畫。
7. LED 開關與 RGB 展演動畫。
8. 故障節點灰化。
9. 備援節點補位。
10. 分批回收。
11. 入艙充電。
12. 問題節點重播短影片。

### 14.4 第四階段：前端介面

請完成：

1. Carrier Dashboard。
2. Canvas 場域編輯器。
3. 艙位矩陣。
4. 電量熱圖。
5. 起飛波次表。
6. 回收波次表。
7. 問題節點播放器。
8. 風險報表頁。
9. 人力降低估算頁。
10. 不顯示核心演算法。

### 14.5 第五階段：安全驗證

請完成：

1. `SECURITY_REVIEW.md`。
2. 測試禁止任何實機飛控輸出。
3. 測試前端沒有核心算法。
4. 測試所有 JSON 都有 `SIMULATION_ONLY`。
5. 測試 Real Flight Gateway 為 disabled stub。
6. 測試下載檔不能包含 mission upload 或控制命令。

---

## 15. 測試案例

### 15.1 20 台小型展示

- 車載艙位：24。
- 主用無人機：20。
- 備援：4。
- 起飛口：2。
- 展演圖形：簡單 Logo。
- 目標：驗證車載分批起飛動畫與回收流程。

### 15.2 50 台商業展示

- 車載艙位：60。
- 主用無人機：50。
- 備援：10。
- 起飛口：4。
- 展演圖形：文字 + Logo。
- 目標：驗證第一張圖到位時間差補償。

### 15.3 200 台大型展示

- 車載航母：4 台。
- 每台車艙位：60。
- 主用無人機：200。
- 備援：40。
- 起飛口：每台 4。
- 目標：驗證多車協同、等待區分層、回收排隊。

### 15.4 故障重播案例

- D037 低電量。
- D084 LED 失效。
- D112 模擬 GPS 漂移。
- D145 未準時到位。
- R2 回收口堵塞。
- 系統要輸出動畫與報表，不輸出控制命令。

---

## 16. 報表輸出

每次模擬完成後產生：

```text
carrier_show_report.pdf
carrier_show_report.html
carrier_show_summary.json
problem_node_replay_D037.mp4
launch_wave_preview.mp4
recovery_wave_preview.mp4
operator_reduction_report.md
```

報表要包含：

- 起飛總時間。
- 回收總時間。
- 最小距離風險。
- 等待區容量風險。
- 電量風險。
- 充電回補時間。
- 備援節點使用率。
- 工作人員需求估算。
- 傳統鋪地方案 vs 車載航母方案比較。

---

## 17. 展示首頁文案

```text
固定點車載無人機航母展演系統

不再依賴大片地面鋪設，不再逐台人工搬運。
系統將無人機收納在改裝電動車或拖車式航母艙內，
透過分批起飛、空中等待、到位時間補償、LED 同步與回收充電模擬，
把無人機展演從大型施工流程，轉化為可重複、可檢查、可視覺化的行動展演平台。

本系統專注於動畫、模擬、審核與教育訓練，
不輸出實機飛控指令，確保設計流程與實體飛行安全審核分層管理。
```

---

## 18. 驗收條件

Claude Code 完成後，必須能做到：

1. 匯入 `carrier_config.json` 產生車載航母場景。
2. 匯入 `drone_bay_inventory.json` 顯示艙位與電量。
3. 自動產生起飛波次模擬。
4. 自動產生回收波次模擬。
5. 產生 Blender 動畫。
6. 產生問題節點重播影片。
7. 顯示人力降低估算。
8. 顯示風險報表。
9. 前端無核心演算法。
10. 系統無任何實機控制輸出能力。

---

## 19. 最重要的架構原則

```text
現在要做的是：
車載航母展演設計、動畫、排程、充電、回收、故障重播、審核報表。

現在不能做的是：
直接控制實機飛行、失效時自動接管真機、輸出可部署飛控任務。

未來可銜接的是：
由合格飛控團隊或原廠 SDK 在獨立 Real Flight Gateway 中，
讀取已簽核、已驗證、不可由前端竄改的資料，
並依照法規、場域、保險、飛手與安全審查執行。
```

---

## 20. 結語

固定點車載航母方案的價值，不只是節省地面空間，而是把無人機展演從「大量人工鋪排」轉成「艙位化、排程化、可重播、可審核、可擴充」的行動展演平台。

這會讓 20 台、50 台、200 台逐步累積經驗時，每次展演的錯誤都能被記錄、重播、模擬與改進。真正的競爭力不是單次飛起來，而是每次展演後都能留下可分析、可優化、可複製的工程資料。

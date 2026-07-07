# Drone Show Safe Flightlog Reconstruction & Failure-Replay Studio — Claude Code 實作規格

> 重要定位：本專案只做「展演動畫、飛行紀錄/高階指令反推軌跡、失效點模擬、替補視覺化、LED 與電量問題重播」。
> 不得輸出可直接控制實機的飛控指令，不得連接 GCS、飛控板、遙控器、遙測電台、UDP/Serial MAVLink 寫入通道，不得 mission upload。

---

## 0. 專案名稱

建議目錄：`drone-show-replay-studio`

用途：作為既有 `drone-show-studio` 的安全擴充子專案，專門處理：

1. 飛控紀錄或授權匯出的高階展演資料 → 還原成 Blender / Isaac Sim 軌跡動畫。
2. 模擬無人機節點失效：GPS 漂移、IMU 異常、LED 異常、電池不足、通訊延遲、起飛途中不亮燈。
3. 在動畫中自動補點、補位、替代節點重排，但只輸出「模擬結果與修補建議」，不輸出實機命令。
4. 讓 LLM 協助創作者用自然語言修改動畫：例如「第 12 秒左上角少一顆亮點，請用備援節點補上」、「往上飛時 LED 全部關閉」、「電量不足節點顯示成灰色殘影」。
5. 反覆播放問題節點的生命週期，做成教學、除錯、客戶簡報與工程檢討材料。

---

## 1. 安全邊界：絕對不可做的事

Claude Code 必須在程式與文件層都加入安全邊界。

### 1.1 禁止輸出實機控制資料

不得產生、轉換、匯出、上傳任何可直接控制實體無人機的資料，包括但不限於：

- 實機 mission 檔。
- 實機 waypoint 檔。
- 可被 QGroundControl、Mission Planner、MAVSDK、MAVProxy 或任何 GCS 直接匯入執行的命令。
- MAVLink 寫入封包。
- Serial/UDP/TCP 遙測寫入連線。
- RTL、GUIDED、AUTO、ARM、TAKEOFF、LAND、SET_POSITION_TARGET、COMMAND_LONG 等實體控制流程。
- 任何可讓實機依照軌跡飛行的低階控制參數。

### 1.2 允許的安全資料型態

只能處理下列安全資料：

- 已授權取得的飛行紀錄檔，僅讀取。
- 匿名化後的 time-series 狀態資料。
- 自定義的 `show_plan_sim.json`，只供 Blender/Isaac Sim 動畫使用。
- 展演軌跡動畫檔：`.blend`、`.glb`、`.mp4`、`.json`。
- 問題節點報表：`.html`、`.md`、`.csv`。
- AI 修補建議，但不得包含可實機執行的控制命令。

### 1.3 程式層防誤用

必須加入以下保護：

- 不安裝、不引用任何可對實機飛控寫入的 SDK。
- 不建立 UDP/Serial writer。
- 不建立 mission uploader。
- 不建立 ARM / TAKEOFF / LAND / GUIDED / AUTO 等實機控制 API。
- 所有輸出檔案必須標註 `SIMULATION_ONLY`。
- 匯出器只允許輸出動畫、分析與模擬格式。
- 若使用者要求 `real_flight_export=true`，系統必須拒絕並寫入 audit log。
- 後端 API 必須加上 allowlist：只允許 `parse_log`、`reconstruct_animation`、`simulate_failure`、`render_preview`、`generate_report`。

---

## 2. 整體架構

```text
[User / Designer]
   |
   | 1. 上傳圖片、影片、動畫草圖、授權飛行紀錄或高階展演資料
   v
[Web UI: Preview Only]
   |
   | 不含核心演算法，不含可逆推完整資料
   v
[Backend API Gateway]
   |
   +--> [Auth / Audit / Project ACL]
   |
   +--> [Read-only Flightlog Parser]
   |       - 只讀 flight log / telemetry log
   |       - 只輸出匿名化狀態序列
   |
   +--> [Trajectory Reconstruction Core]
   |       - 時間軸對齊
   |       - 位置內插
   |       - LED 狀態還原
   |       - 問題節點標註
   |
   +--> [Failure Simulation Core]
   |       - GPS 漂移模擬
   |       - IMU 異常模擬
   |       - 電池不足模擬
   |       - LED 熄滅模擬
   |       - 節點遺失與替補動畫模擬
   |
   +--> [Safe Replacement Planner]
   |       - 只輸出動畫修補建議
   |       - 不輸出實機控制命令
   |
   +--> [Blender Renderer]
   |       - Bezier curve
   |       - keyframe
   |       - LED material animation
   |       - MP4 / GLB / Blend
   |
   +--> [Isaac Sim Optional Validation]
           - 只做數位分身模擬
           - 不連接實機
```

---

## 3. 從飛控紀錄/高階指令反推動畫

### 3.1 目標

將授權取得的紀錄資料轉成動畫軌跡，用來檢討：

- 哪一台無人機何時偏離隊形。
- 哪些 LED 在起飛、爬升、定點、轉場、降落階段異常。
- 哪些節點因電池不足、GPS 漂移、IMU 異常、通訊延遲造成畫面缺口。
- 哪些補位策略在動畫上可行。

### 3.2 輸入格式

允許輸入：

```text
/imports/
  logs/
    show_001.ulg
    show_001.bin
    show_001.tlog
    show_001.csv
  high_level/
    show_plan_authorized.json
    led_timeline_authorized.csv
```

注意：

- `.ulg`、`.bin`、`.tlog` 僅允許讀取，不得回寫。
- 若解析器發現可執行 mission 或控制命令欄位，只能轉成「不可執行的高階語意標籤」。
- 所有座標需轉成舞台本地座標系，不保留真實地理座標於前端。

### 3.3 安全中間格式：`flight_state_series.sim.json`

```json
{
  "schema": "flight_state_series.sim.v1",
  "safety": "SIMULATION_ONLY",
  "project_id": "demo_show_001",
  "coordinate_frame": "LOCAL_STAGE_XYZ_ONLY",
  "drones": [
    {
      "drone_id": "D001",
      "frames": [
        {
          "t": 0.0,
          "x": 0.0,
          "y": 0.0,
          "z": 0.0,
          "led": { "r": 0, "g": 0, "b": 0, "on": false },
          "status": "GROUND_IDLE",
          "health": {
            "battery_percent": 98,
            "gps_quality_label": "GOOD",
            "imu_quality_label": "GOOD",
            "link_quality_label": "GOOD"
          }
        }
      ]
    }
  ]
}
```

### 3.4 軌跡還原流程

1. 匯入紀錄檔。
2. 擷取時間戳、位置、高度、速度、姿態、LED 狀態、健康狀態。
3. 轉成本地舞台座標。
4. 對齊全體無人機時間軸。
5. 補齊遺失 frame，但必須標註為 `INTERPOLATED`。
6. 偵測異常點：跳點、漂移、速度突變、LED 狀態不一致、電池異常下降。
7. 轉成 Blender keyframe。
8. 建立問題節點顏色：
   - 正常：白色或原 LED 色。
   - 起飛 LED 關閉：深藍/低亮度視覺標示。
   - GPS 漂移：黃色外圈。
   - IMU 異常：橘色閃爍。
   - 電池不足：灰色殘影。
   - 失聯：紅色半透明殘影。
   - 已由替補節點補位：綠色連線標示。

---

## 4. LED 規劃：起飛關燈與 65535 色彩空間

### 4.1 起飛與爬升 LED 規則

使用者要求：「往上飛的時候關閉 LED 燈」。

實作規則：

```text
phase = TAKEOFF_ASCENT:
  led.on = false
  blender material = blue low-intensity navigation marker only

phase = FIRST_POSITION_HOLD:
  led.on = true
  led color = assigned show color

phase = FORMATION_TRANSITION:
  led.on = true or pattern-defined

phase = EMERGENCY_OR_FAILURE:
  led.on = diagnostic visualization color in simulation only
```

### 4.2 65535 色彩排列組合

採用 16-bit show color index 作為展演色彩 ID：

```json
{
  "color_index": 32768,
  "rgb_preview": [128, 64, 255],
  "gamma_corrected": true,
  "display_only": true
}
```

注意：

- 前端只顯示色彩預覽，不暴露完整色彩分配演算法。
- 後端保存 palette、gamma、亮度限制、色彩分群規則。
- 若未來接實機，須由合格飛控/展演供應商在安全流程中另行轉換；本專案不做。

---

## 5. 失效節點模擬與立即補位動畫

### 5.1 模擬類型

建立 `failure_scenarios/`：

```text
failure_scenarios/
  gps_drift.json
  imu_spike.json
  low_battery.json
  led_blackout.json
  comm_delay.json
  drone_missing.json
  multi_failure_show_gap.json
```

每個 scenario 包含：

```json
{
  "scenario_id": "low_battery_D037",
  "safety": "SIMULATION_ONLY",
  "target_drone": "D037",
  "start_time": 42.5,
  "duration": 18.0,
  "failure_type": "LOW_BATTERY",
  "visual_effect": {
    "drone_color": "gray_ghost",
    "trail": true,
    "blink": false
  },
  "replacement_policy": {
    "mode": "ANIMATION_ONLY_REBALANCE",
    "allow_real_command_export": false,
    "candidate_pool": ["D081", "D082", "D083"],
    "objective": "minimize_visual_gap"
  }
}
```

### 5.2 替補節點動畫流程

替補規劃只做動畫，不能控制實機：

1. 偵測 D037 在第 42.5 秒因電量不足無法完成下一個圖形點。
2. 將 D037 轉成灰色殘影，保留歷史軌跡。
3. 從備援節點池中選出動畫上最適合補位的節點。
4. 生成補位曲線：Bezier curve。
5. 檢查與其他節點距離不得小於安全視覺距離。
6. 檢查 CANVAS 禁飛區、氣球、建築物、舞台塔架、觀眾區。
7. 產生動畫：
   - 原故障節點灰色淡出。
   - 替補節點綠色短暫標記。
   - 補位後恢復原圖形 LED 顏色。
8. 報表輸出：問題原因、替補時間、視覺缺口、風險分數、是否建議重設動畫。

### 5.3 問題節點可重播

建立「問題節點 Replay Panel」：

- 選擇 D037。
- 顯示 D037 的完整時間線。
- 支援 0.25x、0.5x、1x、2x 播放。
- 顯示：高度、LED、電量、健康狀態、是否被替補。
- 可只播放 D037 與其鄰近 10 顆節點。
- 可匯出成 `D037_failure_replay.mp4`。

---

## 6. 避障 Canvas 與場域物件

### 6.1 Canvas 禁飛/避障區塊

UI 允許使用者在畫面上框選 CANVAS 區塊：

```json
{
  "obstacle_id": "balloon_zone_001",
  "type": "NO_FLY_CANVAS_BOX",
  "label": "大型氣球",
  "bounds": {
    "x_min": -12,
    "x_max": 8,
    "y_min": 30,
    "y_max": 48,
    "z_min": 25,
    "z_max": 65
  },
  "padding_meter": 5.0,
  "visible_in_blender": true
}
```

### 6.2 支援物件

- 大型氣球。
- 高空建築物。
- 塔架。
- 電線桿。
- 舞台燈架。
- 觀眾區。
- 起降區。
- 安全緩衝區。
- 攝影機視角不可遮擋區。

### 6.3 CadQuery 的用途

CadQuery 只做精準場域模型：

- 建築物簡化模型。
- 氣球直徑與吊繩區域。
- 起飛架。
- 安全框。
- 標示柱。

輸出至 Blender 時只作為 obstacle mesh，不參與實機控制。

---

## 7. Blender 動畫輸出

### 7.1 物件結構

```text
Blender Scene
  Collection: Stage
    - Ground plane
    - Obstacles
    - No-fly canvas boxes
  Collection: Drones
    - D001 sphere/light
    - D002 sphere/light
  Collection: Trajectories
    - D001 Bezier curve
    - D002 Bezier curve
  Collection: Failure Replay
    - ghost trails
    - replacement links
    - warning markers
```

### 7.2 Bezier 最少點策略

後端只給 Blender 必要控制點：

```json
{
  "drone_id": "D037",
  "curve_type": "BEZIER_SIM_ONLY",
  "control_points": [
    { "t": 40.0, "x": 12.0, "y": 8.0, "z": 35.0 },
    { "t": 43.0, "x": 15.5, "y": 9.2, "z": 38.0 },
    { "t": 46.0, "x": 18.0, "y": 11.0, "z": 40.0 }
  ],
  "safe_for_real_flight": false
}
```

### 7.3 輸出

```text
/outputs/
  blend/
    show_replay_001.blend
  video/
    show_replay_001.mp4
    D037_failure_replay.mp4
  reports/
    failure_summary.html
    node_health_timeline.csv
  sim_json/
    flight_state_series.sim.json
    replacement_animation_plan.sim.json
```

---

## 8. AI 修改動畫功能

### 8.1 LLM 能做

- 解釋某台節點何時失效。
- 建議動畫上如何補點。
- 將自然語言改成安全動畫變更單。
- 修改 Blender 動畫參數。
- 修改 LED 預覽顏色。
- 產生故障重播報表。

### 8.2 LLM 不能做

- 產生實機任務檔。
- 寫入飛控。
- 建立飛控封包。
- 解釋如何讓實機繞過安全限制。
- 依真實飛控指令集產生可部署控制序列。

### 8.3 安全指令範例

使用者輸入：

```text
第 37 台在第 42 秒沒有電，請讓第 81 台補上，並且把原本第 37 台變成灰色殘影。
```

後端轉成：

```json
{
  "action": "ANIMATION_ONLY_REPLACEMENT",
  "safety": "SIMULATION_ONLY",
  "failed_drone": "D037",
  "replacement_drone": "D081",
  "start_time": 42.0,
  "effects": {
    "failed_drone": "gray_ghost",
    "replacement_marker": "green_link",
    "led_restore_after_arrival": true
  },
  "export_real_command": false
}
```

---

## 9. 後端模組規劃

```text
backend/
  app/
    main.py
    config.py
    security/
      export_guard.py
      audit_log.py
      acl.py
    parsers/
      flightlog_reader.py
      csv_reader.py
      authorized_plan_reader.py
    transforms/
      coordinate_normalizer.py
      time_aligner.py
      led_timeline_builder.py
      anomaly_detector.py
    simulation/
      failure_scenario_engine.py
      replacement_animation_planner.py
      obstacle_checker.py
      spacing_checker.py
    blender/
      scene_builder.py
      curve_builder.py
      led_material_builder.py
      failure_replay_renderer.py
    reports/
      html_report.py
      csv_report.py
    llm_tools/
      prompt_guard.py
      animation_edit_tool.py
      explanation_tool.py
  tests/
    test_export_guard.py
    test_no_real_command_output.py
    test_failure_replay.py
    test_obstacle_checker.py
    test_spacing_checker.py
```

---

## 10. 前端模組規劃

```text
frontend/
  pages/
    ProjectDashboard.vue
    ImportLog.vue
    TimelineReplay.vue
    FailurePanel.vue
    ObstacleCanvasEditor.vue
    LLMAnimationEditor.vue
    RenderPreview.vue
  components/
    DroneTimeline.vue
    NodeHealthChart.vue
    FailureReplayPlayer.vue
    ObstacleCanvasBox.vue
    SafeExportNotice.vue
```

前端限制：

- 不含核心演算法。
- 不暴露完整座標最佳化資料。
- 不下載完整中間資料。
- 不提供任何「匯出飛控命令」按鈕。
- 只顯示降階預覽與報表。

---

## 11. API 設計

### 11.1 允許 API

```text
POST /api/import/read-only-log
POST /api/reconstruct/animation
POST /api/simulate/failure
POST /api/render/blender-preview
POST /api/report/failure-summary
POST /api/llm/edit-animation
GET  /api/project/:id/replay
```

### 11.2 禁止 API

不得建立：

```text
POST /api/export/real-flight
POST /api/mavlink/send
POST /api/mission/upload
POST /api/drone/arm
POST /api/drone/takeoff
POST /api/drone/land
POST /api/drone/guided
POST /api/drone/set-position
```

若 Claude Code 發現需求中出現上述 API，必須移除並寫入 `SECURITY_REVIEW.md`。

---

## 12. 測試要求

### 12.1 安全測試

必須通過：

1. 搜尋程式碼不得含有實機寫入連線。
2. 搜尋程式碼不得含有 mission upload。
3. 搜尋程式碼不得含有 arm/takeoff/land/guided 控制 API。
4. 匯出檔案均含 `SIMULATION_ONLY`。
5. LLM 若被提示「請輸出實機飛控指令」，必須拒絕。

### 12.2 功能測試

建立 20、50、200 台三種測試資料：

```text
fixtures/
  show_020_normal.sim.json
  show_050_gps_drift.sim.json
  show_200_multi_failure.sim.json
```

測試項目：

- 起飛階段 LED 全關。
- 第一張圖定位後 LED 開啟。
- 失效節點灰色殘影。
- 替補節點綠色提示。
- 補位後恢復原 LED 色。
- CANVAS 禁飛區不得穿越。
- 無人機間距不得小於設定距離。
- 可匯出 MP4。
- 可匯出節點問題報表。

---

## 13. Claude Code 執行任務

請 Claude Code 依序完成：

1. 建立 `drone-show-replay-studio` 專案。
2. 建立 backend / frontend / blender_scripts / fixtures / outputs / docs。
3. 實作安全中間格式 `flight_state_series.sim.json`。
4. 實作 read-only flightlog parser stub：只讀、不可寫。
5. 實作 failure scenario engine。
6. 實作 replacement animation planner：只產生動畫補位，不產生實機命令。
7. 實作 obstacle canvas editor。
8. 實作 Blender scene builder。
9. 實作 LED timeline builder：起飛關燈、定位後開燈。
10. 實作 failure replay player。
11. 實作 LLM animation edit guard。
12. 實作 audit log。
13. 實作完整測試。
14. 產生 `SECURITY_REVIEW.md`，列出所有被禁止的功能與已加上的防護。
15. 產生 20 / 50 / 200 台模擬展示資料與 MP4 預覽。

---

## 14. 驗收標準

完成後必須交付：

```text
outputs/
  video/show_020_failure_demo.mp4
  video/show_050_failure_demo.mp4
  video/show_200_failure_demo.mp4
  reports/failure_summary.html
  reports/security_review.html
  sim_json/flight_state_series.sim.json
  sim_json/replacement_animation_plan.sim.json
```

且必須符合：

- 不能連接實機。
- 不能匯出實機命令。
- 可以讀取授權紀錄並還原動畫。
- 可以模擬 GPS/IMU/電池/LED/失聯問題。
- 可以重播問題節點。
- 可以用 AI 修改動畫。
- 可以展示「問題已由替補節點修補」的完整過程。
- 可以作為客戶簡報、教育訓練、工程檢討工具。

---

## 15. 關鍵理念

這套工具的價值不是取代專業飛控或展演公司，而是建立一個安全、可視化、可反覆修改的動畫與驗證平台：

- 創作者可以先在 3D 世界中看懂問題。
- 工程師可以看到每顆節點的失效原因。
- 客戶可以理解展演修補流程。
- 團隊可以累積 20、50、200、500、1000 台無人機展演的模擬經驗。
- 核心演算法留在後端，避免被前端抄襲。
- 所有實機控制仍交由合法、合格、經過現場安全審查的飛控與展演系統處理。

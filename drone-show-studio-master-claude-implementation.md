# drone-show-studio-master — Claude Code 整合版完整實作規格書

> 本文件為整合版主規格，已將下列既有規劃整併為同一份可直接交給 Claude Code 執行的 `.md`：
>
> 1. `drone-show-studio-claude-implementation.md`
> 2. `drone-show-video-reference-fix-claude.md`
> 3. `drone-show-safe-flightlog-reconstruction-claude.md`
> 4. `drone-carrier-launch-station-claude.md`
>
> 並新增你要求的：
>
> 5. **文案 / 概念 → AI 概念圖 → 可飛隊形 → Blender 動畫 → LLM 修改** 的完整工作流。
>
> 本文件目標是讓 Claude Code 在原有功能上直接追加，不要重做、不拆散，並且把所有核心演算法放在後端，避免被抄襲。

---

# 0. 最重要的總原則

## 0.1 專案定位

本專案是：

**無人機群飛展演設計、動畫、模擬、點位工程、車載航母排程、故障回放、概念圖孵化、風險檢查與報表平台**。

第一階段與第二階段都只做：

- 創意發想
- 圖形孵化
- 點位生成
- 動畫預覽
- 路徑可行性檢查
- 避障模擬
- 車載航母起降排程模擬
- 飛行紀錄回放
- 故障節點補位視覺化
- 報表與審核

**不得做成可直接控制真實無人機的飛控命令系統。**

## 0.2 安全與邊界

Claude Code 在本專案中：

- 不得輸出可直接控制實機的 mission 檔、waypoint 檔、arming/takeoff/land/setpoint 指令。
- 不得建立可連到真實飛控板的自動寫入流程。
- 不得提供 MAVLink/UDP/Serial 寫入控制。
- 不得讓前端直接下載完整演算法、權重、規則庫、點位最佳化核心。
- 不得讓前端接觸可逆推出排程邏輯的中間資料。

### 未來接真機的設計原則

現在就預留 **Future Real Flight Gateway** 的資料接口位置，但**不要現在實作**。未來若要接真機，只替換最後一層 Gateway，不重做前面的創意、動畫、模擬、報表系統。

---

# 1. 專案整體目標

你要建立的是一套可逐年累積經驗的無人機展演工程平台，支援：

1. 從 **20 台、50 台、200 台** 開始持續擴展。
2. 從 **單張圖形** 擴展到 **多幕敘事型展演**。
3. 從 **圖片輸入** 擴展到 **影片參考、文字文案、概念圖生成**。
4. 從 **地面平鋪起飛** 擴展到 **固定點電動車載航母／艙位式分批起飛**。
5. 從 **單純動畫** 擴展到 **失效節點回放、補位模擬、風險檢查與教育訓練**。
6. 建立可供未來真機團隊銜接的標準化資料格式。

---

# 2. Claude Code 的總執行要求

## 2.1 目錄

請在目前專案根目錄建立以下整合專案：

```bash
mkdir -p drone-show-studio
cd drone-show-studio
```

並建立以下主要目錄結構：

```text
/drone-show-studio
  /backend
    /api
    /auth
    /jobs
    /storage
    /concept
    /storyboard
    /image_pipeline
    /video_reference
    /formation
    /trajectory
    /obstacle
    /carrier_station
    /replay
    /review
    /render
      /blender_scripts
      /isaac_connector
    /security
  /frontend
  /workers
  /tests
  /docs
  /samples
  /outputs
```

## 2.2 後端技術建議

使用下列技術實作：

- Python 3.11+
- FastAPI
- PostgreSQL
- Redis
- Celery 或 RQ
- MinIO（儲存素材與輸出）
- Blender headless
- 可選：Isaac Sim connector（進階模擬）
- 前端可用 Next.js / React，但只做預覽與管理，不做核心計算

## 2.3 核心演算法禁止放前端

下列內容一律只能在後端執行：

- 文案轉分鏡
- 圖片轉點位
- 點位均勻化
- 隊形分配
- 路徑最佳化
- 避障規劃
- 最小距離碰撞檢查
- 故障補位邏輯
- 車載航母起降波次排程
- 飛行紀錄還原與異常分析
- IP 圖形可飛化規則

前端只能看到：

- 已降階預覽圖
- 已渲染動畫
- 簡化點位視圖
- 報表結果
- 審核狀態

---

# 3. 技術選型與角色分工

## 3.1 Blender：主動畫核心

Blender 是整個系統的主視覺引擎，負責：

1. 場景建立：天空、地面、城市、觀眾視角、舞台、建築、氣球、禁飛區。
2. 每台無人機的代理物件：光點、球體、簡模。
3. Bezier / polyline 飛行軌跡視覺化。
4. 根據後端 JSON 產生 keyframe animation。
5. 輸出 `.blend`、`.mp4`、`.png storyboard`、`.glb preview`。
6. 輸出起飛圖、第一張定位圖、轉場圖、避障圖、風險圖。

## 3.2 CadQuery：參數化 CAD 輔助層

CadQuery 不放在動畫主流程，但很適合：

- 車載航母艙體概念模型
- 起飛艙位結構
- 建築物體量模型
- 高空氣球、塔架、舞台、障礙物幾何
- 需精準尺寸的場域障礙物

也就是說：

- **Blender = 動畫與可視化主流程**
- **CadQuery = 參數化場景/障礙物/艙體幾何來源**

## 3.3 Isaac Sim：高擬真驗證層

Isaac Sim 不要變成每次都要跑的主流程，而是第二階段驗證層，用於：

- 數位分身驗證
- 高風險轉場驗證
- 感測器概念模擬
- ROS 2 / HIL / SIL 的延伸位置
- 複雜障礙場景驗證

結論：

- 日常快速設計與預覽：**Blender**
- 精準場域模型：**CadQuery**
- 高階驗證與數位孿生：**Isaac Sim**

---

# 4. 系統模組總覽

本整合版要一次規劃以下六大模組：

## 4.1 Core Show Studio

- 展演專案管理
- 場景管理
- 無人機數量級管理（20/50/200/...）
- 點位生成
- 路徑規劃
- 動畫輸出
- 報表輸出

## 4.2 Concept-to-Drone-Show

新增你要求的功能：

- 文字主題 → 故事分鏡
- 文案 → AI 概念圖
- 概念圖 → 可飛圖篩選
- 概念圖 → 點位隊形
- LLM 自然語言修改動畫與圖形
- IP 前期孵化流程

## 4.3 Video Reference Fix

- YouTube/授權影片參考分析
- 影格擷取
- 關鍵分鏡整理
- 點位均勻化修正
- 起飛動畫修正

## 4.4 Replay & Failure Reconstruction

- 授權飛行紀錄 / 高階資料 → 動畫回放
- GPS/IMU/LED/電量/通訊異常模擬
- 故障節點補位視覺化
- 問題節點重播與教學分析

## 4.5 Carrier Launch Station

- 電動車載航母 / 拖車艙位式方案
- 分批起飛
- 空中等待區
- 分批回收
- 艙位、充電、健康檢查、下一輪可用性估算
- 人力降低流程

## 4.6 Review & Governance

- 安全檢查
- 點位品質檢查
- 路徑風險檢查
- 報表與審核
- 版本追蹤
- 不可把核心外流到前端

---

# 5. 輸入模式設計（非常重要）

未來操作介面不可只做「上傳圖片」單一路徑，而要支援四大輸入模式。

## 5.1 模式 A：文字創作模式

適用：

- 尚未有圖
- 只有文案
- 想先做主題與故事

輸入：

- 主題名稱
- 國家/文化元素
- 情緒風格
- 預計無人機數量
- 預計幕數
- 是否要車載航母起飛
- 是否要敘事型轉場

輸出：

- 故事主線
- 分鏡腳本
- 每幕概念描述
- 建議圖形類型（線條 / 面狀 / 混合）
- 建議點位密度
- 建議轉場方式

### 範例

輸入：

> 美國精神、莊嚴、大氣、適合 200 台無人機，最後收在國旗與自由女神。

輸出：

1. 星條旗登場
2. Liberty Bell 輪廓
3. 自由女神火炬升起
4. 老鷹展翅
5. 結尾文字與煙火光效

## 5.2 模式 B：概念圖生成模式

適用：

- 沒有 IP
- 只有文案
- 需要先孵化可用形象
- 想在正式 IP 之前先快速試題材

流程：

```text
文案 → LLM 分鏡 → AI 概念圖 → 人工挑選 → 可飛化評分 → 進入點位流程
```

Claude Code 必須新增一個 **Concept Image Gateway**，可接圖像生成服務（你未來可換任何合規的生成模型），但平台內只保留：

- prompt 版本
- 候選概念圖
- 評分紀錄
- 審核結果

### 概念圖評分項目

每張概念圖都要算：

- 主體辨識度
- 輪廓清晰度
- 可點位化程度
- 均勻分布難度
- 轉場友善度
- 20/50/200 台可行度
- 車載分批起飛可行度

## 5.3 模式 C：圖片轉隊形模式

適用：

- 已有圖形
- 已有 logo
- 已有 AI 概念圖
- 已有手繪圖
- 已有 SVG

輸出：

- 輪廓抽取
- 面域抽取
- 骨架抽取
- 點位生成
- 均勻化
- 20 / 50 / 200 台版本預覽

## 5.4 模式 D：影片參考模式

適用：

- 想學節奏
- 想學轉場方式
- 想分析停留時間
- 想分析視覺構圖類型

注意：

- 影片主要用來參考**節奏與分鏡**。
- 不應直接拿影片逐幀當點位來源主體。
- 圖片負責形狀；影片負責節奏。

## 5.5 模式 E：飛行紀錄回放模式

適用：

- 工程檢討
- 教育訓練
- 問題節點重播
- 客戶說明

輸入：

- 授權高階飛行紀錄
- 授權展演資料

輸出：

- 還原動畫
- 異常時間線
- 故障節點視覺化
- 補位模擬結果

---

# 6. Concept-to-Drone-Show：新增完整規劃

這是本次追加的核心。

## 6.1 你真正需要的是「IP 前期孵化工作流」

請 Claude Code 在 `backend/concept/`、`backend/storyboard/`、`backend/image_pipeline/` 建立完整流程。

### 工作流

```text
文案
→ LLM 轉故事腳本
→ 每幕概念描述
→ 呼叫概念圖生成服務
→ 產生候選圖
→ 計算可飛評分
→ 人工挑選與修圖
→ 圖片可飛化
→ 點位生成
→ Blender 預覽
→ LLM 自然語言修改
→ 形成準 IP 資產
```

## 6.2 LLM 可修改的自然語言範例

系統要支援以下類型修改：

- 「自由女神火炬再高一點」
- 「老鷹翅膀再張開一點」
- 「國旗的星星要更整齊」
- 「第一幕更莊嚴、不要太花」
- 「字樣厚一點，辨識更清楚」
- 「把這一幕改成線條感，不要面太滿」
- 「讓 50 台版本也能看得懂」

LLM 不直接改 Blender，而是：

1. 解析意圖
2. 產生結構化修改指令
3. 寫入後端 patch
4. 再由後端重新生成點位與預覽

## 6.3 準 IP 資產管理

請建立 `concept_assets` 與 `design_lineage`：

- 原始文案
- LLM 腳本版本
- 候選概念圖
- 評分結果
- 被選中版本
- 後續人工修正版本
- 對應點位版本
- 最後動畫版本

這樣你未來就算還沒正式 IP，也能逐步累積自己的視覺語言。

---

# 7. 圖形可飛化與點位工程

這一段是動畫品質的核心，也是你之前卡住的重點。

## 7.1 為什麼點位不均勻？

如果直接用：

- 原始 SVG 節點
- 邊緣偵測像素
- 亮像素
- Canny 輪廓點

通常會造成：

- 局部太密
- 直線太稀
- 轉角堆點
- 面域中空洞不均

所以必須改成工程化流程。

## 7.2 標準點位處理流程

### 線條圖形

1. 擷取輪廓 / 骨架
2. 建立 path
3. 做 **等弧長取樣（equal arc-length sampling）**
4. 保證線段間距穩定

### 面狀圖形

1. 擷取主面域
2. 以 **Poisson Disk Sampling** 產生均勻點
3. 以 **Lloyd Relaxation** 做平衡
4. 檢查過密與過稀區

### 混合圖形

1. 主輪廓走等弧長
2. 面域走 Poisson Disk
3. 合併後再全域微調

## 7.3 品質指標

每次生成點位都要輸出：

- `min_spacing`
- `avg_spacing`
- `spacing_cv`
- `too_close_pairs`
- `outlier_density_regions`
- `readability_score`
- `shape_similarity_score`

設定：

- `spacing_cv` 過高直接判定不合格
- 出現太多 `too_close_pairs` 不可進入動畫層

## 7.4 跨幕隊形分配

幕與幕之間不可用「第 N 台對第 N 點」這種粗糙方法。

必須建立成本矩陣，考慮：

- 距離最小化
- 路徑交叉風險
- 避障風險
- 高度變化代價
- 車載起飛波次限制
- 電量與可用性

採用後端 assignment solver 處理。

---

# 8. 起飛動畫修正：必須告訴 Claude 卡在哪裡

你之前卡住的關鍵通常不是美術問題，而是資料與 keyframe 沒做好。

## 8.1 常見錯誤

1. 只畫了 Bezier 軌跡線，沒有真正對 drone object 插 keyframe。
2. 只有最終定位點，沒有起飛→等待→入場的時間序列。
3. 所有無人機同一幀跳到位。
4. 只看到靜態曲線，看不到無人機移動。
5. 起飛波次沒分層，畫面很亂。

## 8.2 正確時間序列

請 Claude Code 強制用以下階段做第一版：

```text
frame 001–060   地面 / 艙位待命，LED off
frame 061–150   垂直上升，LED off
frame 151–240   空中等待區，LED dim blue
frame 241–330   進入第一張圖定位，LED blue
frame 331–420   第一張圖 hold，LED 正式顏色
```

## 8.3 車載航母模式的起飛補充

若使用固定點車載航母方案，需再加：

- 艙位出艙動畫
- 起飛口排隊
- 波次起飛
- 空中等待區分層
- 補償第一張圖到位時間差

## 8.4 必做測試

只要下列任一項失敗，Claude Code 不得繼續做美術後製：

- `test_takeoff_has_keyframes`
- `test_all_drones_have_motion`
- `test_first_hold_reached`
- `test_led_off_during_ascent`
- `test_waiting_zone_staging`

也就是說：

> 如果點位均勻化與起飛 keyframe 沒做好，不要繼續做材質、攝影機、字幕或後製。問題不是不夠漂亮，而是基礎資料結構與動畫序列沒有做好。

---

# 9. YouTube / 影片參考工作包

## 9.1 影片用途

影片主要拿來學：

- 每幕停留多久
- 畫面如何敘事
- 轉場速度
- 鏡頭語言
- 圖形切換節奏
- 文字與圖騰混合方式

## 9.2 處理規則

Claude Code 不要自動繞過平台下載來源影片。若使用者提供合法授權影片檔，放在：

```text
inputs/reference_videos/
```

再由系統擷取：

- 關鍵影格
- contact sheet
- 每幕時間段
- 節奏摘要

## 9.3 輸出文件

- `reference_storyboard.md`
- `reference_contact_sheet.png`
- `reference_scene_timing.json`
- `reference_takeoff_notes.md`

---

# 10. 避障與場域規劃

## 10.1 使用者畫 CANVAS 區塊就要避開

這是你的重要需求。系統要支援使用者在畫面上或平面圖上畫出：

- 禁飛矩形
- 禁飛多邊形
- 高空氣球區
- 高樓建築區
- 舞台塔架區
- 觀眾安全距離區
- 臨時空域限制區

前端只能畫區塊，真正的避障規劃在後端。

## 10.2 三維障礙物模型

要支援：

- 地面建築高度
- 氣球體積
- 塔架 / 燈架
- 車載航母位置
- 空中等待區
- 緩衝層高度
- 不同波次通道

## 10.3 避障策略

後端需計算：

- 是否穿越禁飛區
- 路徑是否距離障礙太近
- 轉場是否需要繞飛
- 波次之間是否互相干擾
- 是否要提高等待區高度層級

---

# 11. LED 與視覺語言

## 11.1 起飛時 LED 關閉

請固定規則：

- 起飛上升階段：LED off
- 到空中等待區：dim blue
- 第一張圖定位完成：blue 或指定定位色
- 正式展演：RGB 動畫

## 11.2 65535 組合的實務化處理

你提到 RGB 三色與大量排列組合。系統不要只做單純「顏色欄位」，而要有：

- 顏色 palette 管理
- 隊形分區上色
- 漸層策略
- 幕與幕的色彩一致性
- 故障節點的特殊顏色（灰 / 綠 / 黃 / 紅）

## 11.3 視覺策略層

每幕要記錄：

- 主色
- 輔色
- 點亮時機
- 漸層/閃爍節奏
- 是否適合 20/50/200 台版本

---

# 12. 車載航母固定點啟動方案

這是你很有特色的差異化設計，必須完整納入主系統。

## 12.1 模組名稱

```text
drone-carrier-station
```

## 12.2 核心概念

無人機不再預設平鋪在大片空地，而是：

- 收納於電動車 / 拖車艙位
- 分批從同一位置起飛
- 進入空中等待區
- 依排程進第一張圖
- 展演結束後分批回艙
- 自動充電
- 健康檢查
- 下一輪待命

## 12.3 目標：降低工作人員數量

系統要用自動化降低：

- 地面鋪點
- 無人機搬運
- 充電管理
- 編號核對
- 回收管理
- 問題節點人工尋找

## 12.4 子功能

- 艙位矩陣管理
- 波次起飛排程
- 空中等待區管理
- 第一張圖到位補償
- 分批回收排程
- 充電狀態監控
- 艙位可用性預測
- 下一輪準備時間估算

---

# 13. 故障回放與補位模擬

## 13.1 模組名稱

```text
drone-show-replay-studio
```

## 13.2 允許的用途

- 授權資料回放
- GPS 漂移模擬
- IMU 異常模擬
- LED 異常模擬
- 電量不足模擬
- 通訊延遲模擬
- 失效節點視覺化
- 補位與替補動畫模擬
- 問題節點反覆重播

## 13.3 表現方式

- 失效節點：灰色殘影
- 補位節點：綠色標記
- 低電量節點：黃色警示
- 通訊異常：紅色斷續狀態

## 13.4 重要限制

只輸出：

- 模擬結果
- 修補建議
- 動畫回放
- 教學材料

**不得輸出實機命令。**

---

# 14. 資料模型與檔案輸出

請標準化以下資料格式：

```text
show_scene.json
storyboard.json
concept_assets.json
formation_frames.json
trajectory_plan.json
led_timeline.json
obstacle_map.json
carrier_schedule.json
risk_report.json
flight_review.json
replay_timeline.json
```

## 14.1 重要欄位

### `storyboard.json`
- scene_id
- title
- prompt_source
- narrative_summary
- concept_image_ids
- formation_type
- drone_count_target
- recommended_transition

### `formation_frames.json`
- frame_group_id
- drone_id
- x, y, z
- color
- formation_role
- confidence

### `trajectory_plan.json`
- drone_id
- route_segments
- bezier_control_points
- estimated_distance
- min_clearance
- risk_flags

### `carrier_schedule.json`
- slot_id
- drone_id
- launch_wave
- launch_time
- recovery_wave
- recovery_time
- charge_status
- next_ready_eta

### `risk_report.json`
- spacing_cv
- too_close_pairs
- obstacle_conflicts
- transition_cost
- battery_risk
- takeoff_stage_risk
- replay_anomalies
- approval_status

---

# 15. API 規劃

請在後端 API 提供高階、安全、不可直接控制真機的接口。

## 15.1 Concept API

- `POST /concept/storyboard/generate`
- `POST /concept/images/generate`
- `POST /concept/images/evaluate`
- `POST /concept/images/select`

## 15.2 Formation API

- `POST /formation/from-image`
- `POST /formation/from-concept`
- `POST /formation/even-spacing`
- `POST /formation/transition/solve`

## 15.3 Animation API

- `POST /animation/takeoff-plan`
- `POST /animation/render/blender`
- `POST /animation/storyboard/export`

## 15.4 Carrier API

- `POST /carrier/layout/create`
- `POST /carrier/launch/simulate`
- `POST /carrier/recovery/simulate`
- `POST /carrier/charge/estimate`

## 15.5 Replay API

- `POST /replay/import`
- `POST /replay/anomaly/simulate`
- `POST /replay/render`
- `POST /replay/patch/suggest`

## 15.6 Review API

- `GET /review/risk-report/{job_id}`
- `POST /review/approve`
- `POST /review/reject`

注意：

- 不提供 mission upload API
- 不提供真機控制 API
- 不提供可直接匯出飛控命令 API

---

# 16. 前端規劃

前端只能做：

- 專案管理
- 文案輸入
- 分鏡編輯
- 概念圖挑選
- 圖片上傳
- 影片參考上傳（授權素材）
- CANVAS 禁飛區塊繪製
- 低解析預覽
- 報表查看
- 審核流程

## 16.1 前端絕對不能做的事

- 不得在瀏覽器端跑核心點位演算法
- 不得下載完整點位內核
- 不得顯示完整權重參數
- 不得存放可逆推核心邏輯的資料

---

# 17. 權限與防抄襲

這是你特別要求的。

## 17.1 角色

- Admin
- Creative Director
- Animation Designer
- Safety Reviewer
- Replay Analyst
- Carrier Operator (simulation only)
- Viewer

## 17.2 防抄襲原則

1. 核心演算法只在後端容器內。
2. 前端只拿預覽圖與報表摘要。
3. 所有重要 JSON 要有權限控制。
4. 敏感資料可做簽章或加密儲存。
5. 記錄誰看過、誰匯出過。
6. 不提供完整可逆推中間結果下載。
7. LLM prompt、權重與規則庫版本列為內部資產。

---

# 18. Claude Code 必做的實作順序

請 Claude Code 不要東做一點、西做一點，而是按下列階段完整推進。

## Phase 1：建立整體骨架

- 專案結構
- 資料模型
- API skeleton
- 任務隊列
- 基本前端頁面

## Phase 2：圖片與概念圖流程

- 文案轉分鏡
- 概念圖接口
- 圖片轉隊形
- 點位均勻化
- 20/50/200 台預覽

## Phase 3：Blender 動畫流程

- 起飛動畫
- 第一張圖定位
- 多幕轉場
- LED 時序
- 輸出影片

## Phase 4：避障與 CANVAS 區塊

- 禁飛區塊
- 建築/氣球/塔架障礙
- 路徑風險檢查

## Phase 5：影片參考修正版工作包

- 影格擷取
- 分鏡節奏分析
- 點位均勻化修補
- 起飛動畫修補

## Phase 6：車載航母模組

- 艙位模型
- 波次起飛
- 空中等待區
- 分批回收
- 充電與下一輪估算

## Phase 7：Replay 與故障回放

- 授權紀錄匯入
- 異常時間線
- 故障補位視覺化
- 教學回放

## Phase 8：審核、報表與防抄襲

- 風險報表
- 權限模型
- 匯出限制
- 稽核軌跡

---

# 19. 測試規格

## 19.1 單元測試

- `test_storyboard_generation`
- `test_concept_image_scoring`
- `test_image_to_formation`
- `test_even_spacing_metrics`
- `test_transition_assignment`
- `test_takeoff_has_keyframes`
- `test_led_off_during_ascent`
- `test_canvas_obstacle_avoidance`
- `test_carrier_wave_schedule`
- `test_replay_import_and_render`
- `test_failure_visualization`
- `test_frontend_cannot_access_core_algorithms`

## 19.2 整合測試

情境至少要做：

1. **文字 → 分鏡 → 概念圖 → 點位 → 動畫**
2. **圖片 → 點位 → 均勻化 → 動畫**
3. **影片參考 → 分鏡節奏 → 修正版動畫**
4. **車載航母起飛 → 等待區 → 第一張圖定位**
5. **故障點回放 → 補位視覺化 → 風險報表**

## 19.3 驗收標準

- 20 台版本可跑通
- 50 台版本可跑通
- 200 台版本可跑通（至少模擬）
- 起飛動畫連續可見
- 點位分布均勻度明顯改善
- 前端看不到核心演算法細節
- 可以由自然語言反覆修改

---

# 20. 交付物

Claude Code 完成時，至少交付：

## 20.1 文件

- `README.md`
- `ARCHITECTURE.md`
- `SECURITY_REVIEW.md`
- `CONCEPT_WORKFLOW.md`
- `CARRIER_STATION.md`
- `REPLAY_WORKFLOW.md`
- `VIDEO_REFERENCE_FIX.md`
- `API_SPEC.md`
- `DEPLOYMENT.md`
- `TEST_PLAN.md`

## 20.2 程式

- 後端 API
- Worker
- Blender 腳本
- 資料模型
- 前端頁面
- 測試程式

## 20.3 範例資料

- 美國主題示範文案
- AI 概念圖示範流程
- 圖片轉隊形示範
- 20 / 50 / 200 台示範
- 車載航母示範
- 故障回放示範

---

# 21. 給 Claude Code 的最終執行指令

請直接在既有 `drone-show-studio` 規劃基礎上做整合式增量開發，**不可重建、不可拆散、不可遺漏原有功能**。你要把原本的：

- 主動畫與模擬平台
- YouTube / 影片參考修正版
- 安全版飛行紀錄還原與故障回放
- 固定點車載航母啟動方案

全部整合進同一套系統，並新增：

- 文案轉分鏡
- AI 概念圖生成接口
- 概念圖可飛化評分
- IP 前期孵化流程
- LLM 自然語言修改隊形與動畫

並且嚴格遵守以下原則：

1. 所有核心演算法留在後端。
2. 前端只做預覽與管理。
3. 不輸出可直接控制實機的飛控命令。
4. 先求 20 台版本穩定，再擴展 50 台與 200 台。
5. 起飛動畫與點位均勻化若未通過測試，不得往下做美術優化。
6. CANVAS 禁飛區塊、建築物、高空氣球、艙位式分批起飛都要納入同一套資料模型。
7. 所有版本、素材、文案、概念圖、點位、動畫與報表都要可追溯。
8. 完成後要能讓使用者用自然語言持續修改創作。

## 執行偏好

- 直接完整實作，不要只做 Demo。
- 優先做可運行主幹與測試。
- 中途不要停下來詢問是否繼續。
- 採用 `/loop` 思維持續修補直到測試通過。
- 每完成一個 Phase 都要補文件與測試。

---

# 22. 一句話總結

這套系統不是單純做「漂亮的無人機動畫」，而是要做成：

**從文案、概念圖、點位工程、動畫預覽、避障模擬、車載航母排程、故障回放，到未來可銜接真機 Gateway 的完整無人機展演設計平台。**


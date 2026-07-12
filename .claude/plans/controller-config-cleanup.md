# 优化控制器配置:去掉 enabled、固化优先级、简化 gaze

## 目标
1. 移除控制器配置的 `enabled` 字段(运行态启停仍由仪表盘开关/MCP `set_controller` 控制)。
2. 所有控制器优先级固化为代码常量,从配置中删除,禁止用户调整。
3. 简化 `GazeControllerSettings` 到 5 个用户旋钮,其余 25 项固化为 gaze 模块私有常量(行为不变)。

## Part 1 — 移除 `enabled` 字段
- `controllers/config.py`:`ControllerSettings` 基类删 `enabled` 字段(行 11)。
- `controllers/base.py`:删 `enabled` 属性(48-49)与 `start()` 守卫 `if not self.enabled`(60-63)。
- `controllers/semantic/expression.py`:删 `start()` 中 `if not self.enabled`(112-114)。
- `controllers/semantic/mouth_sync.py`:删 `start()` 中 `if not self.enabled or ...` 的 enabled 分支(42),保留 `is_running` 守卫。
- `app/base.py`:`ControllerStatus` 删 `enabled` 字段(38);`list_controllers()` 不再传 enabled(218);`set_controller` docstring 去掉"禁用"措辞(225-226)。
- `mcp/toolset.py`:`list_controllers` 返回项去 enabled(218)并改 docstring(212-214);`set_controller` docstring/返回文删"禁用无法启动"(228、236)。
- `gui/bridge/vtubestudio_bridge.py`:`_start_controller` 删 enabled 注释与"已禁用"错误提示(225-230)。
- `scripts/mcp_multi_queue_emotions_test.py`:`c.get("enabled")` 判定改为仅看 `running`(212、328)。

## Part 2 — 优先级固化为常量
- 新建 `controllers/constants.py`:
  - `IDLE_CONTROLLER_PRIORITY = 10`(blink/breathing/gaze/mouth_expression 共用)
  - `MOUTH_SYNC_PRIORITY = 99`、`MOUTH_SYNC_YIELD_PRIORITY = 0`(静音/无音频让出)
  - `EXPRESSION_AU_PRIORITY = 20`、`EXPRESSION_NEUTRAL_PRIORITY = 1`
- `controllers/config.py`:删 `GazeControllerSettings.priority`、`MouthSyncControllerSettings.priority`、`ExpressionControllerSettings.au_priority`/`neutral_priority`。
- `gaze.py`:`priority = self.config.priority` → `IDLE_CONTROLLER_PRIORITY`。
- `blink.py`/`breathing.py`/`mouth_expression.py`:内联 `priority=10` → `IDLE_CONTROLLER_PRIORITY`。
- `mouth_sync.py`:`self.config.priority` → `MOUTH_SYNC_PRIORITY`;让出值 `0` → `MOUTH_SYNC_YIELD_PRIORITY`。
- `expression.py`:`self.config.au_priority`→`EXPRESSION_AU_PRIORITY`(335);`self.config.neutral_priority`→`EXPRESSION_NEUTRAL_PRIORITY`(304、379)。
- 注:`templates/constants.py` 的 `TEMPLATE_PRIORITY=50` 已是常量,不动。

## Part 3 — 简化 gaze 配置(5 旋钮)
- `controllers/config.py` `GazeControllerSettings` 仅保留:
  - `gaze_x_amplitude`(1.0)、`gaze_y_amplitude`(0.85)
  - `head_follow_strength`(新,0~1,默认 1.0;统一缩放头部 yaw/pitch/roll,取代旧 3 个 ratio)
  - `head_follow_chance`(0.55)、`reverse_head_chance`(0.18)
  - 删 `validate_gaze_range`(被删字段全成常量,无需运行时校验)。
- `gaze.py` 顶部新增模块私有常量(取被删字段原默认值):
  - 头部三轴基础因子 `_HEAD_YAW_FACTOR=0.6`/`_HEAD_PITCH_FACTOR=0.18`/`_HEAD_ROLL_FACTOR=0.15`(strength=1.0 复现旧行为)
  - `_HEAD_FOLLOW_DELAY`/`_HEAD_FOLLOW_DURATION`、saccade/fixation/drift/dart/micro 各时长、`_REACH_MIN_SCALE`、`_CENTER_BIAS`/`_CENTER_MICRO_CHANCE`、micro 幅度、`_BALANCE_WINDOW`、`_DRIFT_CHANCE`/`_DART_CHANCE`
  - 引用替换:`__init__` 的 `balance_window`→`_BALANCE_WINDOW`;`_head_targets` 三轴改为 `factor * head_follow_strength * follow_sign`;`_pick_target`/`_pick_style`/`_reach_magnitude`/`run_cycle` 中被删字段→对应常量;保留的 5 字段仍走 `self.config.*`。

## Part 4 — 旧配置迁移(兼容已落盘 YAML)
- `controllers/config.py` `ControllerSettings` 基类加 `model_validator(mode="before")` 剥离废弃键 frozenset:`enabled`/`priority`/`au_priority`/`neutral_priority` + 25 个 gaze 废弃字段。保留各子类 `extra="forbid"` 对其它未知键的拦截。注释标注为迁移垫片,后续可删。
  - 注:`expression/models.py` 的 `SemanticExpressionUnit.enabled`(行 62/81)是表情单元开关,与控制器无关,不动。
- 重新生成 `configs/models/vtubestudio/*.yaml`(6 份):用 `.venv\Scripts\python.exe` 跑一次性脚本,对每份 YAML `ConfigManager(...).load()`(垫片剥离废弃键)再 `.save()`(`model_dump` 只写合法字段),清理为新 schema。

## Part 5 — 测试更新
- `tests/test_platform_model_config.py`、`tests/test_save_model_config.py`:`_with_blink_disabled` 改为修改其它可变字段(如 `blink.min_interval=5.0`)验证 save/load 往返,断言相应调整。
- `tests/test_platform_state_events.py`:`_StubController` 删 `enabled` 参数与守卫;删 `test_set_controller_disabled_broadcasts_not_running`。
- `tests/test_expression_integration.py`:删 `au_priority=`/`neutral_priority=` 构造参数;断言改用 `EXPRESSION_AU_PRIORITY`/`EXPRESSION_NEUTRAL_PRIORITY`;`priority == 0` 检测改 `== EXPRESSION_NEUTRAL_PRIORITY`;更新测试名/注释中的 priority0 字样。
- `tests/test_semantic_controllers.py`:
  - `_mouth_sync` 删 `priority` 参数与 kwarg;`== 99` 改 `== MOUTH_SYNC_PRIORITY`。
  - `test_gaze_controller_outputs_center_micro_jitter`:删被删字段构造参数,改用 monkeypatch gaze 模块常量(`_MICRO_GAZE_X_AMPLITUDE` 等)保留测试意图,断言同步调整。
  - `test_gaze_controller_can_reverse_follow_on_three_head_axes`:`head_follow_ratio/pitch_ratio/roll_ratio` → `head_follow_strength=1.0` + monkeypatch 三轴因子,保留反向三轴断言。
  - `test_gaze_defaults_prefer_fast_center_micro_and_slow_roaming`:改为断言 gaze 模块常量(已移出 config)。

## Part 6 — 自检
- `npx pyright` 类型自检(memory 约定,禁用注释屏蔽)。
- 跑测试:`test_semantic_controllers`、`test_expression_integration`、`test_platform_model_config`、`test_save_model_config`、`test_platform_state_events`、`test_animation_runtime`、`test_tween_engine`、`test_tween_engine_extended`。
- 更新记忆 `mcp-layer`/`app-public-methods-for-mcp`:`list_controllers` 返回不再含 `enabled`。

## 影响面
- 行为:连接后批量启动不再因 `enabled=False` 跳过控制器(用户用仪表盘开关控制运行态);优先级与 gaze 内部参数不再可调,默认值与旧默认一致(行为不变)。
- 公开 API:`ControllerStatus` 去掉 `enabled`;MCP `list_controllers` 返回项去掉 `enabled`。
- 配置兼容:旧 YAML 经迁移垫片可正常加载;6 份 shipped YAML 重新生成。

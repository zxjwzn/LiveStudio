"""控制器优先级常量

各控制器下发语义参数的优先级,用于 tween 引擎的逐参数仲裁(低优先级被运行中的
高优先级拒绝,等高/更高优先级覆盖先到者)。优先级固化为代码常量,不进模型配置、
禁止用户调整,避免误调导致控制器间抢占异常。

约定:
- 待机控制器(blink/breathing/gaze/mouth_expression)统一 ``IDLE_CONTROLLER_PRIORITY``,
  彼此互不竞争同一参数,等高后到覆盖即可。
- 唇形同步说话时独占 MOUTH_OPEN(``MOUTH_SYNC_PRIORITY``);静音/无音频时让出到
  ``MOUTH_SYNC_YIELD_PRIORITY``,使表情解算等可接管。
- 表情过渡/保持段用 ``EXPRESSION_AU_PRIORITY``(高于待机,保护展示期);回归静息段
  用 ``EXPRESSION_NEUTRAL_PRIORITY``(低于待机,待机控制器即时接管)。
"""

from typing import Final

IDLE_CONTROLLER_PRIORITY: Final[int] = 10
MOUTH_SYNC_PRIORITY: Final[int] = 99
MOUTH_SYNC_YIELD_PRIORITY: Final[int] = 0
EXPRESSION_AU_PRIORITY: Final[int] = 20
EXPRESSION_NEUTRAL_PRIORITY: Final[int] = 1

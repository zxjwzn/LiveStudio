## Audio Input

- 默认配置文件位于 `config/audio_input.yaml`
- 可通过 `device_index` 或 `device_name` 指定目标麦克风，二者同时为空时自动选择系统默认输入设备
- 使用 `livestudio.services.audio_input.AudioInputService` 初始化、启动后，可通过 `read_chunk()` 异步读取实时音频块

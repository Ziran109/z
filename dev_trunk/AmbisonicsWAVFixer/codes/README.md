# Ambisonics WAV Fixer

一个零依赖的 Python GUI 工具，用于批量修复 Ambisonics WAV 文件的格式（支持 1OA 至 7OA，即 4 至 64 通道），使其能被 Soundly/Soundminer 正确识别通道信息。

## 问题背景

当从 DAW（如 Pro Tools、Reaper）导出 Ambisonics WAV 文件时，文件通常缺少 iXML 和 bext 元数据，导致 Soundly/Soundminer 无法正确识别通道顺序。

**解决方案**：
- 将 PCM 格式转换为 WAVEFORMATEXTENSIBLE 格式
- 设置正确的 ChannelMask (0x00000000) 和 Ambisonics GUID
- 添加 iXML 和 bext 元数据，包含通道名称信息

## 特性

- **零依赖**：仅使用 Python 标准库，无需安装任何第三方包
- **无损修改**：直接修改文件头，不重新编码音频数据，保证音质无损
- **批量处理**：支持批量处理整个文件夹
- **GUI 界面**：Material Design Dark Theme，直观的图形界面
- **多阶支持**：支持 1OA 至 7OA（4 至 64 通道）Ambisonics 格式
- **通道顺序选择**：支持 ACN (AmbiX) 和 FuMa 两种通道顺序
- **元数据保留**：保留原有的 iXML、bext 等元数据 chunks
- **安全验证**：自动验证文件格式，只处理符合条件的文件
- **详细日志**：清晰的处理状态输出

## 支持的 Ambisonics 阶数

| 阶数 | 通道数 | 说明 |
|------|--------|------|
| 1OA (1st Order) | 4 通道 | W, Y, Z, X (ACN) 或 W, X, Y, Z (FuMa) |
| 2OA (2nd Order) | 9 通道 | 一阶 + 5 个额外通道 |
| 3OA (3rd Order) | 16 通道 | 二阶 + 7 个额外通道 |
| 4OA (4th Order) | 25 通道 | 三阶 + 9 个额外通道 |
| 5OA (5th Order) | 36 通道 | 四阶 + 11 个额外通道 |
| 6OA (6th Order) | 49 通道 | 五阶 + 13 个额外通道 |
| 7OA (7th Order) | 64 通道 | 六阶 + 15 个额外通道 |

## 系统要求

- Python 3.6 或更高版本
- 支持 Windows / macOS / Linux

## 快速开始

### GUI 模式（推荐）

直接运行脚本或使用打包的 .exe 文件：

```bash
python AmbisonicsWAVFixer.py
```

或直接运行 `AmbisonicsWAVFixer_v2.5.2.exe`

操作流程：
1. 选择包含 WAV 文件的输入文件夹
2. 选择通道顺序：
   - **ACN / AmbiX**：默认选项，适用于大多数现代 Ambisonics 工作
   - **FuMa**：传统 Furse-Malham 格式
3. 选择输出模式：
   - **原地修改**：直接修改原文件
   - **选择输出文件夹**：将修改后的文件保存到新位置
4. 点击"开始处理"

### CLI 模式

#### 原地修改

```bash
python AmbisonicsWAVFixer.py --input ./input_wavs --inplace
```

#### 输出到新文件夹

```bash
python AmbisonicsWAVFixer.py --input ./input_wavs --output ./output_wavs
```

#### 指定通道顺序

```bash
# 使用 ACN (AmbiX) 通道顺序（默认）
python AmbisonicsWAVFixer.py --input ./input_wavs --output ./output_wavs --channel-order ACN

# 使用 FuMa 通道顺序
python AmbisonicsWAVFixer.py --input ./input_wavs --output ./output_wavs --channel-order FuMa
```

### 命令行参数

| 参数 | 简写 | 说明 |
|------|------|------|
| `--input` | `-i` | 输入文件夹路径 |
| `--output` | `-o` | 输出文件夹路径（可选） |
| `--inplace` | - | 原地修改文件标志 |
| `--channel-order` | `-c` | 通道顺序：ACN（默认）或 FuMa |
| `--version` | `-v` | 显示版本信息 |
| `--help` | `-h` | 显示帮助信息 |

## 输出示例

```
找到 3 个 WAV 文件 (通道顺序: ACN)
============================================================

[1/3] TEST_protools.wav
  ✓ SUCCESS: 已修复: Mask: 0x003C0000→0, GUID→Ambisonics, iXML添加

[2/3] TEST_reaper.wav
  ✓ SUCCESS: PCM → Extensible (ACN, 44100Hz + iXML添加 + bext保留)

[3/3] zoom_h3vr.wav
  ○ SKIPPED: 已是 Ambisonics 格式

============================================================
处理完成
  成功: 2
  跳过: 1
  错误: 0
```

## 支持的格式

### 输入格式

| 来源 | 格式 | 处理方式 |
|------|------|----------|
| Pro Tools 导出 | WAVEFORMATEXTENSIBLE | 修改 ChannelMask + GUID + 添加 iXML/bext |
| Reaper 导出 | PCM | 转换为 Extensible + 添加 iXML/bext |
| Zoom H3 VR | PCM + iXML/bext | 转换为 Extensible + 保留原有元数据 |
| 其他 Ambisonics Encoder | Extensible | 设置 Ambisonics GUID |

### 输出格式

所有文件统一输出为 WAVEFORMATEXTENSIBLE 格式：
- Format Tag: 0xFFFE (WAVE_FORMAT_EXTENSIBLE)
- Channel Mask: 0x00000000 (KSAUDIO_SPEAKER_DIRECTOUT)
- SubFormat GUID: {00000001-0721-11D3-8644-C8C1CA000000} (AMBISONIC_B_FORMAT)
- iXML chunk: 包含通道名称
- bext chunk: 包含广播元数据

## 通道顺序说明

### ACN (AmbiX) - 默认
通道顺序：W(0), Y(1), Z(2), X(3), ...
- 这是现代 Ambisonics 的标准通道顺序
- YouTube、Facebook 等平台使用此格式
- 大多数 Ambisonics 插件和工具使用此格式

### FuMa (Furse-Malham)
通道顺序：W(0), X(1), Y(2), Z(3), ...
- 传统 Ambisonics 格式
- 早期 Ambisonics 设备和软件使用
- Wwise 自动识别为 FuMa 格式

## 打包为 EXE

使用 PyInstaller 打包为独立的 Windows 可执行文件：

```bash
pyinstaller AmbisonicsWAVFixer_v2.5.2.spec --clean
```

打包后的文件位于 `dist/AmbisonicsWAVFixer_v2.5.2.exe`

## 注意事项

1. **备份重要文件**：建议在处理前备份原始文件，或使用"输出到新文件夹"模式
2. **Ambisonics 文件**：工具支持 1OA 至 7OA（4 至 64 通道）Ambisonics WAV 文件，其他文件会被跳过
3. **Soundly/Soundminer 识别**：处理后的文件可以在 Soundly/Soundminer 中正确显示通道信息
4. **Wwise 识别**：Wwise 会将处理后的文件识别为 FuMa 格式（这是 Wwise 的限制）

## 版本历史

### v2.5.2
- 完整支持 1OA 至 7OA（4 至 64 通道）Ambisonics 格式
- 改进多通道文件处理逻辑
- 优化内存使用，支持大文件处理

### v2.5.0
- 添加高阶 Ambisonics 支持（最高 7OA）
- 改进通道数量自动检测

### v2.4.0
- Material Design Dark Theme 界面
- 移除 emoji 提升性能
- 调整默认窗口大小
- 更新作者信息

### v2.3.0
- 添加 GUI 通道顺序选择（ACN/FuMa）
- 默认使用 ACN (AmbiX) 通道顺序
- 改进 iXML/bext 元数据生成

### v2.2.0
- 保留原有 iXML/bext 元数据 chunks
- 确保 Soundly/Soundminer 能识别通道信息

### v2.1.0
- 支持 PCM 格式转换为 Extensible 格式
- 支持 Reaper 导出的 WAV 文件
- 添加 Ambisonics GUID

### v2.0.0
- 重写为 GUI 界面版本
- 支持 Pro Tools 和 Reaper 导出的各种格式
- 添加输出文件夹选择

### v1.0.0
- 初始版本
- 基本的 ChannelMask 修改功能

## 许可证

MIT License

## 作者

Ziran Da
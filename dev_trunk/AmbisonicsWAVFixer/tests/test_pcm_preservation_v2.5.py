#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自检测试脚本 - 验证 PCM 格式是否正确保留
测试 AmbisonicsWAVFixer v2.5.0 的 PCM 格式保留功能
"""

import os
import sys
import struct
import shutil
from pathlib import Path

# 添加项目路径
project_path = Path(__file__).parent.parent / 'proj_main' / 'AmbisonicsWAVFixer'
sys.path.insert(0, str(project_path))

# 导入处理函数
import importlib.util
spec = importlib.util.spec_from_file_location("AmbisonicsWAVFixer", str(project_path / "AmbisonicsWAVFixer.py"))
ambisonics_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ambisonics_module)

# 从模块获取常量和函数
WAVE_FORMAT_PCM = ambisonics_module.WAVE_FORMAT_PCM
WAVE_FORMAT_EXTENSIBLE = ambisonics_module.WAVE_FORMAT_EXTENSIBLE
process_wav_file = ambisonics_module.process_wav_file
read_all_chunks = ambisonics_module.read_all_chunks
find_chunk = ambisonics_module.find_chunk
parse_fmt_chunk = ambisonics_module.parse_fmt_chunk

def create_test_pcm_wav(output_path, num_channels=4, sample_rate=48000, bits_per_sample=24):
    """
    创建一个测试用的 PCM 格式 WAV 文件。
    
    参数:
        output_path: 输出文件路径
        num_channels: 通道数
        sample_rate: 采样率
        bits_per_sample: 位深度
    """
    # 计算参数
    block_align = num_channels * (bits_per_sample // 8)
    byte_rate = sample_rate * block_align
    
    # 创建 fmt chunk 数据 (PCM 格式，16 字节)
    fmt_data = bytearray(16)
    struct.pack_into('<H', fmt_data, 0, WAVE_FORMAT_PCM)  # wFormatTag = 0x0001
    struct.pack_into('<H', fmt_data, 2, num_channels)      # nChannels
    struct.pack_into('<I', fmt_data, 4, sample_rate)       # nSamplesPerSec
    struct.pack_into('<I', fmt_data, 8, byte_rate)         # nAvgBytesPerSec
    struct.pack_into('<H', fmt_data, 12, block_align)      # nBlockAlign
    struct.pack_into('<H', fmt_data, 14, bits_per_sample)  # wBitsPerSample
    
    # 创建简单的音频数据 (1秒的静音)
    num_samples = sample_rate
    audio_data_size = num_samples * block_align
    audio_data = bytes(audio_data_size)
    
    # 计算文件大小
    # RIFF header (4) + file_size (4) + WAVE (4) = 12
    # fmt chunk: 8 + 16 = 24
    # data chunk: 8 + audio_data_size
    file_size = 4 + 24 + 8 + audio_data_size
    
    # 写入文件
    with open(output_path, 'wb') as f:
        f.write(b'RIFF')
        f.write(struct.pack('<I', file_size))
        f.write(b'WAVE')
        
        # fmt chunk
        f.write(b'fmt ')
        f.write(struct.pack('<I', 16))
        f.write(fmt_data)
        
        # data chunk
        f.write(b'data')
        f.write(struct.pack('<I', audio_data_size))
        f.write(audio_data)
    
    print(f"创建测试 PCM WAV 文件: {output_path}")
    print(f"  通道数: {num_channels}")
    print(f"  采样率: {sample_rate} Hz")
    print(f"  位深度: {bits_per_sample} bits")
    print(f"  格式: PCM (0x0001)")

def verify_pcm_format(file_path):
    """
    验证文件是否为 PCM 格式。
    
    返回:
        dict: 包含格式信息
    """
    with open(file_path, 'rb') as f:
        # 验证 RIFF/WAVE
        riff = f.read(4)
        if riff != b'RIFF':
            return {'error': "不是 RIFF 文件"}
        
        file_size = struct.unpack('<I', f.read(4))[0]
        wave = f.read(4)
        if wave != b'WAVE':
            return {'error': "不是 WAVE 文件"}
        
        # 读取所有 chunks
        chunks = read_all_chunks(f)
        
        # 查找 fmt chunk
        fmt_chunk = find_chunk(chunks, b'fmt ')
        if fmt_chunk is None:
            return {'error': "找不到 fmt chunk"}
        
        # 解析 fmt chunk
        fmt_info = parse_fmt_chunk(fmt_chunk)
        if fmt_info is None:
            return {'error': "无法解析 fmt chunk"}
        
        return {
            'format_tag': fmt_info['format_tag'],
            'format_name': 'PCM' if fmt_info['format_tag'] == WAVE_FORMAT_PCM else 'Extensible',
            'channels': fmt_info['channels'],
            'sample_rate': fmt_info['sample_rate'],
            'bits_per_sample': fmt_info['bits_per_sample'],
            'fmt_chunk_size': fmt_chunk['size'],
            'has_ixml': find_chunk(chunks, b'iXML') is not None,
            'has_bext': find_chunk(chunks, b'bext') is not None,
        }

def run_test():
    """运行自检测试。"""
    print("=" * 60)
    print("AmbisonicsWAVFixer v2.5.0 - PCM 格式保留自检测试")
    print("=" * 60)
    
    # 创建测试目录
    test_dir = Path(__file__).parent.parent / 'ext_files' / 'ambisonics_channelMask_fixer' / 'output_test'
    test_dir.mkdir(parents=True, exist_ok=True)
    
    # 测试不同通道数
    test_cases = [
        {'channels': 4, 'name': 'FOA'},
        {'channels': 9, 'name': '2OA'},
        {'channels': 16, 'name': '3OA'},
    ]
    
    all_passed = True
    
    for case in test_cases:
        num_channels = case['channels']
        order_name = case['name']
        
        print(f"\n--- 测试 {order_name} ({num_channels} 通道) ---")
        
        # 创建测试文件
        input_file = test_dir / f'test_pcm_{order_name}.wav'
        output_file = test_dir / f'test_pcm_{order_name}_processed.wav'
        
        # 删除旧文件
        if input_file.exists():
            input_file.unlink()
        if output_file.exists():
            output_file.unlink()
        
        # 创建 PCM 测试文件
        create_test_pcm_wav(str(input_file), num_channels=num_channels)
        
        # 验证输入文件格式
        input_info = verify_pcm_format(str(input_file))
        print(f"\n输入文件格式验证:")
        print(f"  Format Tag: 0x{input_info['format_tag']:04X} ({input_info['format_name']})")
        print(f"  fmt chunk 大小: {input_info['fmt_chunk_size']} 字节")
        print(f"  通道数: {input_info['channels']}")
        print(f"  iXML: {'有' if input_info['has_ixml'] else '无'}")
        print(f"  bext: {'有' if input_info['has_bext'] else '无'}")
        
        # 处理文件
        print(f"\n处理文件...")
        status, message = process_wav_file(str(input_file), str(output_file), 
                                           in_place=False, log_callback=print,
                                           channel_order='AmbiX')
        print(f"处理结果: {status} - {message}")
        
        # 验证输出文件格式
        output_info = verify_pcm_format(str(output_file))
        print(f"\n输出文件格式验证:")
        print(f"  Format Tag: 0x{output_info['format_tag']:04X} ({output_info['format_name']})")
        print(f"  fmt chunk 大小: {output_info['fmt_chunk_size']} 字节")
        print(f"  通道数: {output_info['channels']}")
        print(f"  iXML: {'有' if output_info['has_ixml'] else '无'}")
        print(f"  bext: {'有' if output_info['has_bext'] else '无'}")
        
        # 检查 PCM 格式是否保留
        if output_info['format_tag'] == WAVE_FORMAT_PCM:
            print(f"\n✓ 测试通过: PCM 格式已正确保留!")
            print(f"  fmt chunk 大小保持 {output_info['fmt_chunk_size']} 字节 (PCM 标准)")
        else:
            print(f"\n✗ 测试失败: PCM 格式被转换为 Extensible!")
            print(f"  Format Tag: 0x{output_info['format_tag']:04X}")
            all_passed = False
        
        # 检查元数据是否添加
        if output_info['has_ixml'] and output_info['has_bext']:
            print(f"✓ 元数据已添加: iXML 和 bext chunks 存在")
        else:
            print(f"✗ 元数据添加失败")
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("所有测试通过! PCM 格式保留功能正常工作。")
    else:
        print("测试失败! PCM 格式保留功能存在问题。")
    print("=" * 60)
    
    return all_passed

if __name__ == '__main__':
    success = run_test()
    sys.exit(0 if success else 1)
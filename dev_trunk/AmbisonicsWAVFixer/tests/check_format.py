#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查 WAV 文件格式"""

import struct
import sys
from pathlib import Path

# 添加项目路径
project_path = Path(__file__).parent.parent / 'proj_main' / 'AmbisonicsWAVFixer'
sys.path.insert(0, str(project_path))

import importlib.util
spec = importlib.util.spec_from_file_location("AmbisonicsWAVFixer", str(project_path / "AmbisonicsWAVFixer.py"))
ambisonics_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ambisonics_module)

WAVE_FORMAT_PCM = ambisonics_module.WAVE_FORMAT_PCM
WAVE_FORMAT_EXTENSIBLE = ambisonics_module.WAVE_FORMAT_EXTENSIBLE
read_all_chunks = ambisonics_module.read_all_chunks
find_chunk = ambisonics_module.find_chunk
parse_fmt_chunk = ambisonics_module.parse_fmt_chunk


def check_wav_format(file_path):
    """检查 WAV 文件格式"""
    print(f"\n检查文件: {file_path}")
    print("=" * 60)
    
    with open(file_path, 'rb') as f:
        # RIFF header
        riff = f.read(4)
        if riff != b'RIFF':
            print("错误: 不是 RIFF 文件")
            return
        
        file_size = struct.unpack('<I', f.read(4))[0]
        wave = f.read(4)
        if wave != b'WAVE':
            print("错误: 不是 WAVE 文件")
            return
        
        print(f"RIFF header: {riff.decode()}")
        print(f"File size: {file_size} bytes")
        print(f"WAVE type: {wave.decode()}")
        
        # 读取所有 chunks
        chunks = read_all_chunks(f)
        
        # 列出所有 chunks
        print(f"\nChunks 列表:")
        for chunk in chunks:
            chunk_name = chunk['id'].decode('ascii', errors='replace')
            print(f"  {chunk_name}: {chunk['size']} bytes")
        
        # 解析 fmt chunk
        fmt_chunk = find_chunk(chunks, b'fmt ')
        if fmt_chunk is None:
            print("\n错误: 找不到 fmt chunk")
            return
        
        fmt_info = parse_fmt_chunk(fmt_chunk)
        if fmt_info is None:
            print("\n错误: 无法解析 fmt chunk")
            return
        
        print(f"\nfmt chunk 详细信息:")
        print(f"  fmt chunk 大小: {fmt_chunk['size']} bytes")
        print(f"  Format Tag: 0x{fmt_info['format_tag']:04X}")
        
        if fmt_info['format_tag'] == WAVE_FORMAT_PCM:
            print(f"  格式类型: PCM (标准 PCM)")
        elif fmt_info['format_tag'] == WAVE_FORMAT_EXTENSIBLE:
            print(f"  格式类型: Extensible (扩展格式)")
            if 'channel_mask' in fmt_info:
                print(f"  Channel Mask: 0x{fmt_info['channel_mask']:08X}")
            if 'subformat' in fmt_info:
                subformat = fmt_info['subformat']
                # 检查是否是 PCM GUID
                pcm_guid = bytes([0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x10, 0x00, 
                                  0x80, 0x00, 0x00, 0xAA, 0x00, 0x38, 0x9B, 0x71])
                ambisonic_guid = bytes([0x01, 0x00, 0x00, 0x00, 0x21, 0x07, 0xD3, 0x11,
                                        0x86, 0x44, 0xC8, 0xC1, 0xCA, 0x00, 0x00, 0x00])
                if subformat == pcm_guid:
                    print(f"  SubFormat: PCM GUID")
                elif subformat == ambisonic_guid:
                    print(f"  SubFormat: Ambisonic B-Format GUID")
                else:
                    print(f"  SubFormat: {subformat.hex()}")
        else:
            print(f"  格式类型: 未知")
        
        print(f"  通道数: {fmt_info['channels']}")
        print(f"  采样率: {fmt_info['sample_rate']} Hz")
        print(f"  位深度: {fmt_info['bits_per_sample']} bits")
        print(f"  字节率: {fmt_info['byte_rate']} bytes/sec")
        print(f"  块对齐: {fmt_info['block_align']} bytes")
        
        # 检查 data chunk
        data_chunk = find_chunk(chunks, b'data')
        if data_chunk:
            print(f"\n音频数据:")
            print(f"  数据大小: {len(data_chunk['data'])} bytes")
            duration = len(data_chunk['data']) / fmt_info['byte_rate']
            print(f"  时长: {duration:.2f} 秒")


if __name__ == '__main__':
    # 检查测试文件
    test_dir = Path(__file__).parent.parent / 'ext_files' / 'ambisonics_channelMask_fixer'
    
    files = [
        test_dir / 'TEST_protools.wav',
        test_dir / 'TEST_reaper.wav',
    ]
    
    for f in files:
        if f.exists():
            check_wav_format(str(f))
        else:
            print(f"\n文件不存在: {f}")
#!/usr/bin/env python3
"""分析 Wwise 能正确识别的 Ambisonics 样本文件"""

import os
import struct
import sys

# 添加项目路径
sys.path.insert(0, 'proj_main/ambisonics_wav_fixer')
from ambisonics_wav_fixer import read_all_chunks, find_chunk, parse_fmt_chunk, AMBISONIC_B_FORMAT_GUID_BYTES

def analyze_wav_detailed(filepath):
    """详细分析 WAV 文件"""
    print(f'\n{"="*70}')
    print(f'文件: {os.path.basename(filepath)}')
    print(f'{"="*70}')
    
    with open(filepath, 'rb') as f:
        # RIFF header
        riff = f.read(4)
        file_size = struct.unpack('<I', f.read(4))[0]
        wave = f.read(4)
        print(f'RIFF: {riff}, File Size: {file_size}')
        
        # 读取所有 chunks
        chunks = read_all_chunks(f)
        
        print(f'\n总 Chunks 数: {len(chunks)}')
        for chunk in chunks:
            print(f'  {chunk["id"]} (size: {chunk["size"]})')
        
        # 详细分析 fmt chunk
        fmt_chunk = find_chunk(chunks, b'fmt ')
        if fmt_chunk:
            print(f'\n--- fmt chunk 详细分析 ---')
            fmt_info = parse_fmt_chunk(fmt_chunk)
            print(f'  Format Tag: 0x{fmt_info["format_tag"]:04X}')
            print(f'  Channels: {fmt_info["channels"]}')
            print(f'  Sample Rate: {fmt_info["sample_rate"]}')
            print(f'  Bits Per Sample: {fmt_info["bits_per_sample"]}')
            
            if fmt_info['channel_mask'] is not None:
                print(f'  Channel Mask: 0x{fmt_info["channel_mask"]:08X}')
            if fmt_info['subformat'] is not None:
                print(f'  SubFormat (raw): {fmt_info["subformat"].hex()}')
                
                # 比较 GUID
                if fmt_info['subformat'] == AMBISONIC_B_FORMAT_GUID_BYTES:
                    print(f'  SubFormat: ✓  AMBISONIC_B_FORMAT GUID (Wwise 兼容)')
                else:
                    print(f'  SubFormat: ✗ 不是 AMBISONIC_B_FORMAT GUID')
                    print(f'  期望的 GUID: {AMBISONIC_B_FORMAT_GUID_BYTES.hex()}')
        
        # 检查 iXML
        ixml_chunk = find_chunk(chunks, b'iXML')
        if ixml_chunk:
            print(f'\n--- iXML chunk ---')
            print(f'  Size: {ixml_chunk["size"]}')
            try:
                data = ixml_chunk['data']
                # 找到有效 UTF-8 部分
                valid_end = 0
                for i in range(len(data)):
                    try:
                        data[:i+1].decode('utf-8')
                        valid_end = i + 1
                    except:
                        break
                preview = data[:min(valid_end, 500)].decode('utf-8')
                print(f'  内容预览:\n{preview}')
            except Exception as e:
                print(f'  解析错误: {e}')
        
        # 检查 bext
        bext_chunk = find_chunk(chunks, b'bext')
        if bext_chunk:
            print(f'\n--- bext chunk ---')
            print(f'  Size: {bext_chunk["size"]}')
            try:
                desc = bext_chunk['data'][0:256].rstrip(b'\x00').decode('utf-8', errors='ignore')
                print(f'  Description 预览: {desc[:200]}')
            except:
                pass

# 分析 Wwise 样本文件
sample_file = 'ext_files/ambisonics_channelMask_fixer/SLS101_AKWAL_Countryside Open Field_bMTR_LP.amb'
if os.path.exists(sample_file):
    analyze_wav_detailed(sample_file)
else:
    print(f'文件不存在: {sample_file}')

# 分析我们工具处理后的文件
processed_file = 'ext_files/ambisonics_channelMask_fixer/output_test/260324_008_fixed.WAV'
if os.path.exists(processed_file):
    print(f'\n\n{"="*70}')
    print('我们工具处理后的文件 (新版本)')
    print(f'{"="*70}')
    analyze_wav_detailed(processed_file)
else:
    print(f'\n文件不存在: {processed_file}')
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ambisonics WAV Fixer v2.5.2
===========================
一个零依赖的 Python GUI 工具，用于批量处理 Ambisonics WAV 文件，
为其添加 iXML/bext 元数据，确保 Soundly/Soundminer 能正确识别通道信息。

支持的场景：
1. Pro Tools 导出的 WAV（Extensible 格式）→ 转换为 PCM 格式 + 添加 iXML/bext 元数据
2. Reaper 导出的 WAV（PCM 格式）→ 保留 PCM 格式 + 添加 iXML/bext 元数据
3. Zoom H3 VR 录音机直出（PCM + iXML）→ 保留 PCM 格式 + 保留 iXML/bext 元数据
4. Encoder 后手动制作的 Ambisonics → 转换为 PCM 格式 + 添加 iXML/bext 元数据

支持的 Ambisonics 阶数：
- FOA (1阶): 4 通道
- 2OA (2阶): 9 通道
- 3OA (3阶): 16 通道
- 4OA (4阶): 25 通道
- 5OA (5阶): 36 通道
- 6OA (6阶): 49 通道
- 7OA (7阶): 64 通道

关键改进：
- 所有输出文件统一为 PCM 格式（16字节 fmt chunk），避免 Extensible 格式的潜在兼容性问题
- 保留所有元数据 chunks（iXML, bext, JUNK 等）
- PCM 格式文件保留原有 fmt chunk
- Extensible 格式文件转换为标准 PCM 格式
- 支持 AmbiX (ACN) 和 FuMa 两种通道顺序
- 支持 FOA 到 7OA 的所有阶数
- Material Design Dark Theme 界面
- 使用微软雅黑字体，确保中英文显示一致

作者: Ziran Da
版本: 2.5.2
"""

import os
import sys
import struct
import shutil
import threading
import ctypes
import subprocess
from pathlib import Path

# 导入 tkinter
import tkinter as tk
from tkinter import filedialog, ttk, scrolledtext

# ============================================================================
# DPI 感知设置（Windows 高DPI支持）
# ============================================================================
try:
    # Windows 10+ DPI 感知
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        # Windows 8.1+ DPI 感知
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # PROCESS_SYSTEM_DPI_AWARE
    except Exception:
        pass


# ============================================================================
# 常量定义
# ============================================================================

# WAV 文件格式常量
WAVE_FORMAT_PCM = 0x0001
WAVE_FORMAT_EXTENSIBLE = 0xFFFE
FMT_CHUNK_SIZE_PCM = 16
FMT_CHUNK_SIZE_EXTENSIBLE = 40
RIFF_HEADER_SIZE = 12
CHUNK_HEADER_SIZE = 8

# 偏移量常量
OFFSET_FORMAT_TAG = 0
OFFSET_CHANNELS = 2
OFFSET_CHANNEL_MASK = 20
OFFSET_SUBFORMAT = 24

# 声道掩码
CHANNEL_MASK_DIRECTOUT = 0x00000000

# SubFormat GUID for Wwise Ambisonics recognition
# Wwise 识别 Ambisonics 需要使用 AMBISONIC_B_FORMAT GUID + Channel Mask = 0
# AMBISONIC_B_FORMAT GUID: {00000001-0721-11D3-8644-C8C1CA000000}
# 这是 DirectX Media Objects 中的 MEDIASUBTYPE_AMBISONIC_B_FORMAT
# 参考: https://docs.microsoft.com/en-us/windows/win32/directshow/ambisonic--b-format--subtypes
AMBISONIC_B_FORMAT_GUID_BYTES = bytes([
    0x01, 0x00, 0x00, 0x00,  # Data1: 00000001 (小端序)
    0x21, 0x07,              # Data2: 0721 (小端序)
    0xD3, 0x11,              # Data3: 11D3 (小端序)
    0x86, 0x44, 0xC8, 0xC1, 0xCA, 0x00, 0x00, 0x00  # Data4
])

# Ambisonics 阶数与通道数对应关系
# 通道数 = (order + 1)^2
AMBISONICS_ORDERS = {
    'FOA': {'order': 1, 'channels': 4, 'name': 'FOA (1阶, 4通道)'},
    '2OA': {'order': 2, 'channels': 9, 'name': '2OA (2阶, 9通道)'},
    '3OA': {'order': 3, 'channels': 16, 'name': '3OA (3阶, 16通道)'},
    '4OA': {'order': 4, 'channels': 25, 'name': '4OA (4阶, 25通道)'},
    '5OA': {'order': 5, 'channels': 36, 'name': '5OA (5阶, 36通道)'},
    '6OA': {'order': 6, 'channels': 49, 'name': '6OA (6阶, 49通道)'},
    '7OA': {'order': 7, 'channels': 64, 'name': '7OA (7阶, 64通道)'},
}

# ACN (AmbiX) 通道名称 - 根据 ACN 序号命名
# ACN 序号 n 对应的通道名称为 ACNn
def get_acn_channel_names(num_channels):
    """获取 ACN (AmbiX) 通道名称列表。"""
    names = []
    for i in range(num_channels):
        names.append(f'ACN{i}')
    return names

# FuMa 通道名称 - 传统 Furse-Malham 通道命名
# FOA: W, X, Y, Z
# 2OA: W, X, Y, Z, R, S, T, U, V
# 3OA+: 使用扩展命名
def get_fuma_channel_names(num_channels):
    """获取 FuMa 通道名称列表。"""
    # FuMa 传统命名（最多16通道有传统名称）
    fuma_traditional = [
        'W', 'X', 'Y', 'Z',           # 0-3 (FOA)
        'R', 'S', 'T', 'U', 'V',      # 4-8 (2OA)
        'K', 'L', 'M', 'N', 'O', 'P', 'Q', # 9-15 (3OA部分)
    ]
    
    if num_channels <= len(fuma_traditional):
        return fuma_traditional[:num_channels]
    else:
        # 超过传统命名范围，使用 FuMa_n 格式
        names = fuma_traditional[:]
        for i in range(len(fuma_traditional), num_channels):
            names.append(f'FuMa{i}')
        return names


# ============================================================================
# WAV 文件解析函数
# ============================================================================

def read_all_chunks(f):
    """
    读取 WAV 文件中的所有 chunks（包括 fmt 之前的 chunks）。
    
    返回:
        list: [{'id': chunk_id, 'size': chunk_size, 'data': chunk_data}, ...]
    """
    chunks = []
    
    # 跳过 RIFF header (12 bytes)
    f.seek(RIFF_HEADER_SIZE)
    
    while True:
        chunk_offset = f.tell()
        chunk_id = f.read(4)
        if len(chunk_id) < 4:
            break
        
        chunk_size_data = f.read(4)
        if len(chunk_size_data) < 4:
            break
        
        chunk_size = struct.unpack('<I', chunk_size_data)[0]
        
        # 读取 chunk 数据
        chunk_data = f.read(chunk_size)
        
        # 处理填充字节
        if chunk_size % 2 == 1:
            f.read(1)  # 跳过填充字节
        
        chunks.append({
            'id': chunk_id,
            'offset': chunk_offset,
            'size': chunk_size,
            'data': chunk_data
        })
    
    return chunks


def find_chunk(chunks, chunk_id):
    """
    在 chunks 列表中查找指定 ID 的 chunk。
    
    返回:
        dict 或 None
    """
    for chunk in chunks:
        if chunk['id'] == chunk_id:
            return chunk
    return None


def parse_fmt_chunk(fmt_chunk):
    """
    解析 fmt chunk 数据。
    
    返回:
        dict: 格式信息
    """
    data = fmt_chunk['data']
    size = fmt_chunk['size']
    
    if len(data) < 16:
        return None
    
    result = {
        'format_tag': struct.unpack('<H', data[0:2])[0],
        'channels': struct.unpack('<H', data[2:4])[0],
        'sample_rate': struct.unpack('<I', data[4:8])[0],
        'byte_rate': struct.unpack('<I', data[8:12])[0],
        'block_align': struct.unpack('<H', data[12:14])[0],
        'bits_per_sample': struct.unpack('<H', data[14:16])[0],
        'channel_mask': 0,
        'subformat': None
    }
    
    if size >= 40 and result['format_tag'] == WAVE_FORMAT_EXTENSIBLE:
        if len(data) >= 40:
            result['channel_mask'] = struct.unpack('<I', data[20:24])[0]
            result['subformat'] = data[24:40]
    
    return result


def create_extensible_fmt_data(fmt_info):
    """
    创建 Extensible 格式的 fmt chunk 数据。
    
    返回:
        bytes: 40 字节的 fmt chunk 数据
    """
    data = bytearray(40)
    
    # wFormatTag = 0xFFFE (Extensible)
    struct.pack_into('<H', data, 0, WAVE_FORMAT_EXTENSIBLE)
    
    # nChannels
    struct.pack_into('<H', data, 2, fmt_info['channels'])
    
    # nSamplesPerSec
    struct.pack_into('<I', data, 4, fmt_info['sample_rate'])
    
    # nAvgBytesPerSec
    struct.pack_into('<I', data, 8, fmt_info['byte_rate'])
    
    # nBlockAlign
    struct.pack_into('<H', data, 12, fmt_info['block_align'])
    
    # wBitsPerSample
    struct.pack_into('<H', data, 14, fmt_info['bits_per_sample'])
    
    # cbSize = 22 (扩展数据大小)
    struct.pack_into('<H', data, 16, 22)
    
    # wValidBitsPerSample = wBitsPerSample
    struct.pack_into('<H', data, 18, fmt_info['bits_per_sample'])
    
    # dwChannelMask = 0 (KSAUDIO_SPEAKER_DIRECTOUT)
    struct.pack_into('<I', data, 20, CHANNEL_MASK_DIRECTOUT)
    
    # SubFormat = AMBISONIC_B_FORMAT GUID (Wwise Ambisonics 识别)
    data[24:40] = AMBISONIC_B_FORMAT_GUID_BYTES
    
    return bytes(data)


def is_ambisonic_b_format_guid(guid_bytes):
    """检查是否为 AMBISONIC_B_FORMAT GUID。"""
    return guid_bytes == AMBISONIC_B_FORMAT_GUID_BYTES


def get_ambisonics_order_from_channels(channels):
    """
    根据通道数判断 Ambisonics 阶数。
    
    返回:
        str: 阶数名称 ('FOA', '2OA', 等) 或 None
    """
    for order_name, info in AMBISONICS_ORDERS.items():
        if info['channels'] == channels:
            return order_name
    return None


def create_ixml_chunk(channel_order='AmbiX', num_channels=4):
    """
    创建 iXML chunk 数据。
    
    参数:
        channel_order: 'AmbiX' (ACN) 或 'FuMa'
        num_channels: 通道数量
    
    返回:
        bytes: iXML chunk 数据
    """
    if channel_order == 'AmbiX':
        # AmbiX/ACN 通道顺序
        tracks = [(i+1, name) for i, name in enumerate(get_acn_channel_names(num_channels))]
    else:
        # FuMa 通道顺序
        tracks = [(i+1, name) for i, name in enumerate(get_fuma_channel_names(num_channels))]
    
    ixml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<BWFXML>
<IXML_VERSION>1.62</IXML_VERSION>
<TRACK_LIST>
<TRACK_COUNT>{num_channels}</TRACK_COUNT>
'''
    for idx, name in tracks:
        ixml_content += f'''<TRACK>
<CHANNEL_INDEX>{idx}</CHANNEL_INDEX>
<INTERLEAVE_INDEX>{idx}</INTERLEAVE_INDEX>
<NAME>{name}</NAME>
</TRACK>
'''
    
    ixml_content += '''</TRACK_LIST>
</BWFXML>'''
    
    return ixml_content.encode('utf-8')


def create_bext_chunk(channel_order='AmbiX', num_channels=4):
    """
    创建 bext chunk 数据。
    
    参数:
        channel_order: 'AmbiX' (ACN) 或 'FuMa'
        num_channels: 通道数量
    
    返回:
        bytes: bext chunk 数据 (最小 602 字节)
    """
    if channel_order == 'AmbiX':
        # AmbiX/ACN 通道顺序
        channel_names = get_acn_channel_names(num_channels)
    else:
        # FuMa 通道顺序
        channel_names = get_fuma_channel_names(num_channels)
    
    # 构建 zTRK 信息
    trk_info = ''
    for i, name in enumerate(channel_names):
        trk_info += f'zTRK{i+1}={name}\n'
    
    # bext chunk 结构:
    # Description (256 bytes) + Originator (32 bytes) + OriginatorReference (32 bytes) +
    # OriginationDate (10 bytes) + OriginationTime (8 bytes) + TimeReference (8 bytes) +
    # Version (2 bytes) + UMID (64 bytes) + LoudnessValue (2 bytes) + LoudnessRange (2 bytes) +
    # MaxTruePeakLevel (2 bytes) + MaxMomentaryLoudness (2 bytes) + MaxShortTermLoudness (2 bytes) +
    # Reserved (180 bytes) + CodingHistory (variable)
    
    bext_data = bytearray(602)  # 最小大小
    
    # Description (256 bytes)
    desc_bytes = trk_info.encode('utf-8')
    bext_data[0:len(desc_bytes)] = desc_bytes
    
    # Originator (32 bytes) - 留空
    # 其他字段保持为 0
    
    return bytes(bext_data)


# ============================================================================
# 文件处理函数
# ============================================================================

def add_metadata_to_pcm(input_path, output_path, log_callback=None, channel_order='AmbiX',
                        num_channels=4, has_ixml=False, has_bext=False):
    """
    为 PCM 格式的 WAV 文件添加 iXML/bext 元数据，保留原有 PCM 格式。
    
    参数:
        input_path: 输入文件路径
        output_path: 输出文件路径
        log_callback: 日志回调函数
        channel_order: 通道顺序 ('AmbiX' 或 'FuMa')
        num_channels: 期望的通道数量
        has_ixml: 是否已有 iXML chunk
        has_bext: 是否已有 bext chunk
    
    关键改进：保留所有原有的元数据 chunks（iXML, bext 等）
              保留原有 PCM fmt chunk（16字节），不转换为 Extensible 格式
              如果没有 iXML/bext，则添加通道信息
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
    
    try:
        with open(input_path, 'rb') as f:
            # 验证 RIFF/WAVE
            riff = f.read(4)
            if riff != b'RIFF':
                return 'ERROR', "不是有效的 RIFF 文件"
            
            file_size = struct.unpack('<I', f.read(4))[0]
            wave = f.read(4)
            if wave != b'WAVE':
                return 'ERROR', "不是有效的 WAV 文件"
            
            # 读取所有 chunks（包括 fmt 之前的 iXML, bext 等）
            chunks = read_all_chunks(f)
            
            # 查找 fmt chunk
            fmt_chunk = find_chunk(chunks, b'fmt ')
            if fmt_chunk is None:
                return 'ERROR', "找不到 fmt chunk"
            
            # 解析 fmt chunk
            fmt_info = parse_fmt_chunk(fmt_chunk)
            if fmt_info is None:
                return 'ERROR', "无法解析 fmt chunk"
            
            # 验证格式
            if fmt_info['format_tag'] != WAVE_FORMAT_PCM:
                return 'ERROR', f"非 PCM 格式 (0x{fmt_info['format_tag']:04X})"
            
            # 获取实际通道数并判断阶数
            actual_channels = fmt_info['channels']
            ambisonics_order = get_ambisonics_order_from_channels(actual_channels)
            
            if ambisonics_order is None:
                return 'SKIPPED', f"非 Ambisonics 通道数 ({actual_channels} 通道)"
            
            # 查找 data chunk
            data_chunk = find_chunk(chunks, b'data')
            if data_chunk is None:
                return 'ERROR', "找不到 data chunk"
            
            audio_data = data_chunk['data']
        
        # 保留原有 PCM fmt chunk 数据（不转换为 Extensible）
        original_fmt_data = fmt_chunk['data']
        original_fmt_size = fmt_chunk['size']
        
        # 准备要添加的 iXML 和 bext 数据
        new_ixml_data = None
        new_bext_data = None
        
        if not has_ixml:
            new_ixml_data = create_ixml_chunk(channel_order, actual_channels)
            log(f"添加 iXML chunk ({channel_order}, {ambisonics_order})")
        
        if not has_bext:
            new_bext_data = create_bext_chunk(channel_order, actual_channels)
            log(f"添加 bext chunk ({channel_order}, {ambisonics_order})")
        
        # 计算新文件大小
        # RIFF header (4) + file_size (4) + WAVE (4) = 12
        # 原有 fmt chunk: chunk_id (4) + size (4) + data (原大小)
        # 其他 chunks (保留原有，除了 fmt 和 data)
        # 新增的 iXML 和 bext chunks
        # data chunk: chunk_id (4) + size (4) + audio_data
        
        other_chunks_size = 0
        for chunk in chunks:
            if chunk['id'] not in [b'fmt ', b'data']:
                # chunk header (8) + data (含填充)
                chunk_total = 8 + chunk['size']
                if chunk['size'] % 2 == 1:
                    chunk_total += 1  # 填充字节
                other_chunks_size += chunk_total
        
        # fmt chunk 大小（保留原有 PCM fmt）
        fmt_chunk_total = 8 + original_fmt_size
        if original_fmt_size % 2 == 1:
            fmt_chunk_total += 1  # 填充字节
        
        # 新增 chunks 的大小
        new_chunks_size = 0
        if new_ixml_data:
            ixml_size = len(new_ixml_data)
            new_chunks_size += 8 + ixml_size + (ixml_size % 2)
        if new_bext_data:
            bext_size = len(new_bext_data)
            new_chunks_size += 8 + bext_size + (bext_size % 2)
        
        new_file_size = 4 + (fmt_chunk_total + other_chunks_size + new_chunks_size + 8 + len(audio_data))
        
        # 写入新文件
        with open(output_path, 'wb') as f:
            # RIFF header
            f.write(b'RIFF')
            f.write(struct.pack('<I', new_file_size))
            f.write(b'WAVE')
            
            # 保留原有 fmt chunk (PCM 格式)
            f.write(b'fmt ')
            f.write(struct.pack('<I', original_fmt_size))
            f.write(original_fmt_data)
            # 写入填充字节（如果需要）
            if original_fmt_size % 2 == 1:
                f.write(b'\x00')
            
            # 写入其他 chunks（保留原有元数据，包括 iXML, bext 等）
            for chunk in chunks:
                if chunk['id'] not in [b'fmt ', b'data']:
                    f.write(chunk['id'])
                    f.write(struct.pack('<I', chunk['size']))
                    f.write(chunk['data'])
                    # 写入填充字节（如果需要）
                    if chunk['size'] % 2 == 1:
                        f.write(b'\x00')
            
            # 写入新增的 iXML chunk
            if new_ixml_data:
                f.write(b'iXML')
                f.write(struct.pack('<I', len(new_ixml_data)))
                f.write(new_ixml_data)
                if len(new_ixml_data) % 2 == 1:
                    f.write(b'\x00')
            
            # 写入新增的 bext chunk
            if new_bext_data:
                f.write(b'bext')
                f.write(struct.pack('<I', len(new_bext_data)))
                f.write(new_bext_data)
                if len(new_bext_data) % 2 == 1:
                    f.write(b'\x00')
            
            # data chunk
            f.write(b'data')
            f.write(struct.pack('<I', len(audio_data)))
            f.write(audio_data)
        
        # 构建结果信息
        extra_info = ""
        if has_ixml:
            extra_info += " + iXML保留"
        else:
            extra_info += " + iXML添加"
        if has_bext:
            extra_info += " + bext保留"
        else:
            extra_info += " + bext添加"
        
        return 'SUCCESS', f"PCM (添加元数据) ({channel_order}, {ambisonics_order}, {fmt_info['sample_rate']}Hz{extra_info})"
    
    except Exception as e:
        return 'ERROR', f"处理失败: {e}"


def convert_extensible_to_pcm(input_path, output_path, log_callback=None, channel_order='AmbiX',
                               num_channels=4, has_ixml=False, has_bext=False):
    """
    将 Extensible 格式的 WAV 文件转换为 PCM 格式，并添加 iXML/bext 元数据。
    
    参数:
        input_path: 输入文件路径
        output_path: 输出文件路径
        log_callback: 日志回调函数
        channel_order: 通道顺序 ('AmbiX' 或 'FuMa')
        num_channels: 期望的通道数量
        has_ixml: 是否已有 iXML chunk
        has_bext: 是否已有 bext chunk
    
    关键改进：
        - 将 Extensible 格式（40字节 fmt chunk）转换为标准 PCM 格式（16字节 fmt chunk）
        - 保留所有原有的元数据 chunks（iXML, bext, JUNK 等）
        - 音频数据完全不变
        - 添加 iXML/bext 元数据（如果不存在）
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
    
    try:
        with open(input_path, 'rb') as f:
            # 验证 RIFF/WAVE
            riff = f.read(4)
            if riff != b'RIFF':
                return 'ERROR', "不是有效的 RIFF 文件"
            
            file_size = struct.unpack('<I', f.read(4))[0]
            wave = f.read(4)
            if wave != b'WAVE':
                return 'ERROR', "不是有效的 WAV 文件"
            
            # 读取所有 chunks
            chunks = read_all_chunks(f)
            
            # 查找 fmt chunk
            fmt_chunk = find_chunk(chunks, b'fmt ')
            if fmt_chunk is None:
                return 'ERROR', "找不到 fmt chunk"
            
            # 解析 fmt chunk
            fmt_info = parse_fmt_chunk(fmt_chunk)
            if fmt_info is None:
                return 'ERROR', "无法解析 fmt chunk"
            
            # 验证格式
            if fmt_info['format_tag'] != WAVE_FORMAT_EXTENSIBLE:
                return 'ERROR', f"非 Extensible 格式 (0x{fmt_info['format_tag']:04X})"
            
            # 获取实际通道数并判断阶数
            actual_channels = fmt_info['channels']
            ambisonics_order = get_ambisonics_order_from_channels(actual_channels)
            
            if ambisonics_order is None:
                return 'SKIPPED', f"非 Ambisonics 通道数 ({actual_channels} 通道)"
            
            # 查找 data chunk
            data_chunk = find_chunk(chunks, b'data')
            if data_chunk is None:
                return 'ERROR', "找不到 data chunk"
            
            audio_data = data_chunk['data']
        
        # 创建新的 PCM fmt chunk 数据（16字节）
        # PCM fmt chunk 结构：
        # wFormatTag (2) + nChannels (2) + nSamplesPerSec (4) + nAvgBytesPerSec (4) + nBlockAlign (2) + wBitsPerSample (2)
        pcm_fmt_data = bytearray(16)
        struct.pack_into('<H', pcm_fmt_data, 0, WAVE_FORMAT_PCM)  # wFormatTag = 0x0001
        struct.pack_into('<H', pcm_fmt_data, 2, fmt_info['channels'])
        struct.pack_into('<I', pcm_fmt_data, 4, fmt_info['sample_rate'])
        struct.pack_into('<I', pcm_fmt_data, 8, fmt_info['byte_rate'])
        struct.pack_into('<H', pcm_fmt_data, 12, fmt_info['block_align'])
        struct.pack_into('<H', pcm_fmt_data, 14, fmt_info['bits_per_sample'])
        
        log(f"转换 Extensible → PCM ({ambisonics_order}, {actual_channels}通道)")
        
        # 准备要添加的 iXML 和 bext 数据
        new_ixml_data = None
        new_bext_data = None
        
        if not has_ixml:
            new_ixml_data = create_ixml_chunk(channel_order, actual_channels)
            log(f"添加 iXML chunk ({channel_order}, {ambisonics_order})")
        
        if not has_bext:
            new_bext_data = create_bext_chunk(channel_order, actual_channels)
            log(f"添加 bext chunk ({channel_order}, {ambisonics_order})")
        
        # 计算新文件大小
        # RIFF header (4) + file_size (4) + WAVE (4) = 12
        # PCM fmt chunk: chunk_id (4) + size (4) + data (16) = 24
        # 其他 chunks (保留原有，除了 fmt 和 data)
        # 新增的 iXML 和 bext chunks
        # data chunk: chunk_id (4) + size (4) + audio_data
        
        other_chunks_size = 0
        for chunk in chunks:
            if chunk['id'] not in [b'fmt ', b'data']:
                # chunk header (8) + data (含填充)
                chunk_total = 8 + chunk['size']
                if chunk['size'] % 2 == 1:
                    chunk_total += 1  # 填充字节
                other_chunks_size += chunk_total
        
        # PCM fmt chunk 大小（固定 16 字节）
        fmt_chunk_total = 8 + 16  # chunk header + 16 bytes data
        
        # 新增 chunks 的大小
        new_chunks_size = 0
        if new_ixml_data:
            ixml_size = len(new_ixml_data)
            new_chunks_size += 8 + ixml_size + (ixml_size % 2)
        if new_bext_data:
            bext_size = len(new_bext_data)
            new_chunks_size += 8 + bext_size + (bext_size % 2)
        
        new_file_size = 4 + (fmt_chunk_total + other_chunks_size + new_chunks_size + 8 + len(audio_data))
        
        # 写入新文件
        with open(output_path, 'wb') as f:
            # RIFF header
            f.write(b'RIFF')
            f.write(struct.pack('<I', new_file_size))
            f.write(b'WAVE')
            
            # 写入 PCM fmt chunk (16字节)
            f.write(b'fmt ')
            f.write(struct.pack('<I', 16))  # fmt chunk size = 16
            f.write(pcm_fmt_data)
            
            # 写入其他 chunks（保留原有元数据，包括 iXML, bext, JUNK 等）
            for chunk in chunks:
                if chunk['id'] not in [b'fmt ', b'data']:
                    f.write(chunk['id'])
                    f.write(struct.pack('<I', chunk['size']))
                    f.write(chunk['data'])
                    # 写入填充字节（如果需要）
                    if chunk['size'] % 2 == 1:
                        f.write(b'\x00')
            
            # 写入新增的 iXML chunk
            if new_ixml_data:
                f.write(b'iXML')
                f.write(struct.pack('<I', len(new_ixml_data)))
                f.write(new_ixml_data)
                if len(new_ixml_data) % 2 == 1:
                    f.write(b'\x00')
            
            # 写入新增的 bext chunk
            if new_bext_data:
                f.write(b'bext')
                f.write(struct.pack('<I', len(new_bext_data)))
                f.write(new_bext_data)
                if len(new_bext_data) % 2 == 1:
                    f.write(b'\x00')
            
            # data chunk
            f.write(b'data')
            f.write(struct.pack('<I', len(audio_data)))
            f.write(audio_data)
        
        # 构建结果信息
        extra_info = ""
        if has_ixml:
            extra_info += " + iXML保留"
        else:
            extra_info += " + iXML添加"
        if has_bext:
            extra_info += " + bext保留"
        else:
            extra_info += " + bext添加"
        
        return 'SUCCESS', f"Extensible→PCM ({channel_order}, {ambisonics_order}, {fmt_info['sample_rate']}Hz{extra_info})"
    
    except Exception as e:
        return 'ERROR', f"处理失败: {e}"


def fix_extensible_file(file_path, log_callback=None, channel_order='AmbiX',
                         num_channels=4, has_ixml=False, has_bext=False):
    """
    修复 Extensible 格式文件的 ChannelMask 和 GUID。
    
    直接修改文件，不改变其他 chunks。
    如果缺少 iXML 或 bext，会添加这些 chunks。
    
    注意：v2.5.2 版本中，此函数已被 convert_extensible_to_pcm 替代，
    所有 Extensible 格式文件都会被转换为 PCM 格式输出。
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
    
    try:
        with open(file_path, 'rb+') as f:
            # 验证 RIFF/WAVE
            if f.read(4) != b'RIFF':
                return 'ERROR', "不是有效的 RIFF 文件"
            f.read(4)  # file size
            if f.read(4) != b'WAVE':
                return 'ERROR', "不是有效的 WAV 文件"
            
            # 读取所有 chunks
            chunks = read_all_chunks(f)
            
            # 查找 fmt chunk
            fmt_chunk = find_chunk(chunks, b'fmt ')
            if fmt_chunk is None:
                return 'ERROR', "找不到 fmt chunk"
            
            # 解析 fmt chunk
            fmt_info = parse_fmt_chunk(fmt_chunk)
            if fmt_info is None:
                return 'ERROR', "无法解析 fmt chunk"
            
            # 验证格式
            if fmt_info['format_tag'] != WAVE_FORMAT_EXTENSIBLE:
                return 'ERROR', f"非 Extensible 格式 (0x{fmt_info['format_tag']:04X})"
            
            # 获取实际通道数并判断阶数
            actual_channels = fmt_info['channels']
            ambisonics_order = get_ambisonics_order_from_channels(actual_channels)
            
            if ambisonics_order is None:
                return 'SKIPPED', f"非 Ambisonics 通道数 ({actual_channels} 通道)"
            
            # 检查当前值
            current_mask = fmt_info['channel_mask']
            current_guid = fmt_info['subformat']
            
            mask_correct = (current_mask == CHANNEL_MASK_DIRECTOUT)
            guid_correct = is_ambisonic_b_format_guid(current_guid) if current_guid else False
            
            # 检查是否需要添加 iXML/bext
            need_ixml = not has_ixml
            need_bext = not has_bext
            
            if mask_correct and guid_correct and not need_ixml and not need_bext:
                return 'SKIPPED', f"已是 Ambisonics 格式 ({ambisonics_order})"
            
            # 如果需要添加 iXML 或 bext，需要重写整个文件
            if need_ixml or need_bext:
                log(f"  添加 iXML/bext 元数据 ({channel_order}, {ambisonics_order})...")
                
                # 读取音频数据
                data_chunk = find_chunk(chunks, b'data')
                if data_chunk is None:
                    return 'ERROR', "找不到 data chunk"
                audio_data = data_chunk['data']
                
                # 创建新的 iXML 和 bext 数据
                new_ixml_data = create_ixml_chunk(channel_order, actual_channels) if need_ixml else None
                new_bext_data = create_bext_chunk(channel_order, actual_channels) if need_bext else None
                
                # 计算新文件大小
                new_size = 4  # 'WAVE'
                # fmt chunk
                new_size += 8 + fmt_chunk['size']
                if fmt_chunk['size'] % 2 == 1:
                    new_size += 1
                # 其他 chunks（保留原有元数据）
                for chunk in chunks:
                    if chunk['id'] not in [b'fmt ', b'data']:
                        new_size += 8 + chunk['size']
                        if chunk['size'] % 2 == 1:
                            new_size += 1
                # 新增 iXML
                if new_ixml_data:
                    new_size += 8 + len(new_ixml_data)
                    if len(new_ixml_data) % 2 == 1:
                        new_size += 1
                # 新增 bext
                if new_bext_data:
                    new_size += 8 + len(new_bext_data)
                    if len(new_bext_data) % 2 == 1:
                        new_size += 1
                # data chunk
                new_size += 8 + len(audio_data)
                
                # 创建新的 Extensible fmt 数据
                new_fmt_data = create_extensible_fmt_data(fmt_info)
                
                # 重写文件
                f.seek(0)
                f.write(b'RIFF')
                f.write(struct.pack('<I', new_size))
                f.write(b'WAVE')
                
                # 写入 fmt chunk
                f.write(b'fmt ')
                f.write(struct.pack('<I', len(new_fmt_data)))
                f.write(new_fmt_data)
                
                # 写入其他 chunks（保留原有元数据）
                for chunk in chunks:
                    if chunk['id'] not in [b'fmt ', b'data']:
                        f.write(chunk['id'])
                        f.write(struct.pack('<I', chunk['size']))
                        f.write(chunk['data'])
                        if chunk['size'] % 2 == 1:
                            f.write(b'\x00')
                
                # 写入新增的 iXML chunk
                if new_ixml_data:
                    f.write(b'iXML')
                    f.write(struct.pack('<I', len(new_ixml_data)))
                    f.write(new_ixml_data)
                    if len(new_ixml_data) % 2 == 1:
                        f.write(b'\x00')
                
                # 写入新增的 bext chunk
                if new_bext_data:
                    f.write(b'bext')
                    f.write(struct.pack('<I', len(new_bext_data)))
                    f.write(new_bext_data)
                    if len(new_bext_data) % 2 == 1:
                        f.write(b'\x00')
                
                # 写入 data chunk
                f.write(b'data')
                f.write(struct.pack('<I', len(audio_data)))
                f.write(audio_data)
                
                # 截断文件（如果新文件比原文件小）
                f.truncate()
                
                changes = []
                if not mask_correct:
                    changes.append(f"Mask: 0x{current_mask:08X}→0")
                if not guid_correct:
                    changes.append("GUID→Ambisonics")
                if need_ixml:
                    changes.append("iXML添加")
                if need_bext:
                    changes.append("bext添加")
                
                return 'SUCCESS', f"已修复 ({ambisonics_order}): {', '.join(changes)}"
            
            # 只修改 ChannelMask 和 GUID（不需要添加 iXML/bext）
            # fmt chunk 数据部分起始位置 = chunk offset + 8 (header)
            fmt_data_offset = fmt_chunk['offset'] + 8
            
            # 修改 ChannelMask (偏移 20)
            f.seek(fmt_data_offset + OFFSET_CHANNEL_MASK)
            f.write(struct.pack('<I', CHANNEL_MASK_DIRECTOUT))
            
            # 修改 SubFormat GUID (偏移 24) - 使用 AMBISONIC_B_FORMAT GUID
            f.seek(fmt_data_offset + OFFSET_SUBFORMAT)
            f.write(AMBISONIC_B_FORMAT_GUID_BYTES)
            
            f.flush()
            
            changes = []
            if not mask_correct:
                changes.append(f"Mask: 0x{current_mask:08X}→0")
            if not guid_correct:
                changes.append("GUID→Ambisonics")
            
            return 'SUCCESS', f"已修复 ({ambisonics_order}): {', '.join(changes)}"
    
    except Exception as e:
        return 'ERROR', f"修复失败: {e}"


def process_wav_file(file_path, output_path=None, in_place=False, log_callback=None, 
                     channel_order='AmbiX', num_channels=None):
    """
    处理单个 WAV 文件，自动检测格式并选择合适的处理方式。
    
    参数:
        file_path: 输入文件路径
        output_path: 输出文件路径
        in_place: 是否原地修改
        log_callback: 日志回调函数
        channel_order: 通道顺序 ('AmbiX' 或 'FuMa')
        num_channels: 期望的通道数量（None 表示自动检测）
    """
    try:
        with open(file_path, 'rb') as f:
            # 验证 RIFF/WAVE
            if f.read(4) != b'RIFF':
                return 'ERROR', "不是有效的 RIFF 文件"
            f.read(4)
            if f.read(4) != b'WAVE':
                return 'ERROR', "不是有效的 WAV 文件"
            
            # 读取所有 chunks
            chunks = read_all_chunks(f)
            
            # 查找 fmt chunk
            fmt_chunk = find_chunk(chunks, b'fmt ')
            if fmt_chunk is None:
                return 'ERROR', "找不到 fmt chunk"
            
            # 解析 fmt chunk
            fmt_info = parse_fmt_chunk(fmt_chunk)
            if fmt_info is None:
                return 'ERROR', "无法解析 fmt chunk"
            
            # 获取实际通道数并判断阶数
            actual_channels = fmt_info['channels']
            ambisonics_order = get_ambisonics_order_from_channels(actual_channels)
            
            if ambisonics_order is None:
                return 'SKIPPED', f"非 Ambisonics 通道数 ({actual_channels} 通道)"
            
            # 检查是否有 iXML 和 bext
            has_ixml = find_chunk(chunks, b'iXML') is not None
            has_bext = find_chunk(chunks, b'bext') is not None
        
        # 根据格式选择处理方式
        if fmt_info['format_tag'] == WAVE_FORMAT_PCM:
            # PCM 格式：保留原有格式，仅添加 iXML/bext 元数据
            if in_place:
                temp_path = file_path + '.tmp'
                status, message = add_metadata_to_pcm(file_path, temp_path, log_callback,
                                                       channel_order, actual_channels, 
                                                       has_ixml, has_bext)
                if status == 'SUCCESS':
                    os.replace(temp_path, file_path)
                else:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                return status, message
            elif output_path:
                return add_metadata_to_pcm(file_path, output_path, log_callback,
                                            channel_order, actual_channels, 
                                            has_ixml, has_bext)
            else:
                new_path = file_path.replace('.wav', '_ambisonics.wav')
                return add_metadata_to_pcm(file_path, new_path, log_callback,
                                            channel_order, actual_channels, 
                                            has_ixml, has_bext)
        
        elif fmt_info['format_tag'] == WAVE_FORMAT_EXTENSIBLE:
            # Extensible 格式：转换为 PCM 格式输出
            if in_place:
                temp_path = file_path + '.tmp'
                status, message = convert_extensible_to_pcm(file_path, temp_path, log_callback,
                                                            channel_order, actual_channels,
                                                            has_ixml, has_bext)
                if status == 'SUCCESS':
                    os.replace(temp_path, file_path)
                else:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                return status, message
            elif output_path:
                return convert_extensible_to_pcm(file_path, output_path, log_callback,
                                                  channel_order, actual_channels,
                                                  has_ixml, has_bext)
            else:
                new_path = file_path.replace('.wav', '_ambisonics.wav')
                return convert_extensible_to_pcm(file_path, new_path, log_callback,
                                                  channel_order, actual_channels,
                                                  has_ixml, has_bext)
        
        else:
            return 'ERROR', f"未知格式 (0x{fmt_info['format_tag']:04X})"
    
    except Exception as e:
        return 'ERROR', f"处理失败: {e}"


# ============================================================================
# GUI 界面
# ============================================================================

class AmbisonicsFixerGUI:
    """Ambisonics WAV Fixer GUI 界面 - Material Design Dark Theme。"""
    
    # Material Design Dark Theme Colors
    COLORS = {
        'background': '#121212',          # Main background
        'surface': '#1E1E1E',             # Card/surface background
        'surface_light': '#2D2D2D',       # Elevated surface
        'primary': '#BB86FC',             # Primary color (purple)
        'primary_variant': '#3700B3',     # Primary dark variant
        'secondary': '#03DAC6',           # Secondary color (teal)
        'on_background': '#FFFFFF',       # Text on background
        'on_surface': '#FFFFFF',          # Text on surface
        'on_surface_secondary': '#B0B0B0', # Secondary text
        'error': '#CF6679',               # Error color
        'success': '#03DAC6',             # Success color
        'warning': '#FFAB00',             # Warning/skipped color
        'info': '#BB86FC',                # Info color
    }
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Ambisonics WAV Fixer")
        
        # 设置窗口可调整大小
        self.root.resizable(True, True)
        
        # 设置深色背景
        self.root.configure(bg=self.COLORS['background'])
        
        # 基准字体大小（默认显示时的字体大小）
        self.base_font_size = 10
        
        # 存储所有需要缩放的字体控件
        self.scalable_widgets = []
        
        # 输出目录引用（用于打开文件夹功能）
        self.last_output_dir = None
        
        # 创建自定义样式
        self.setup_styles()
        self.setup_ui()
        
        # 自动调整窗口大小以适应内容
        self.root.update_idletasks()
        
        # 获取内容所需大小
        req_width = self.root.winfo_reqwidth()
        req_height = self.root.winfo_reqheight()
        
        # 设置合理的最小窗口大小（允许缩小）
        min_width = 500
        min_height = 400
        self.root.minsize(min_width, min_height)
        
        # 获取屏幕尺寸并计算合适的位置
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # 默认窗口大小：使用内容所需大小，但不超过屏幕的80%
        default_width = min(req_width + 20, int(screen_width * 0.8))
        default_height = min(req_height + 10, int(screen_height * 0.8))
        
        # 确保默认大小至少能显示主要内容
        default_width = max(default_width, 600)
        default_height = max(default_height, 550)
        
        # 设置基准窗口大小为实际默认窗口大小（用于缩放计算）
        # 这样在默认窗口大小时，缩放比例为 1.0
        self.base_window_width = default_width
        self.base_window_height = default_height
        
        # 居中显示
        x = (screen_width - default_width) // 2
        y = (screen_height - default_height) // 2
        self.root.geometry(f'{default_width}x{default_height}+{x}+{y}')
        
        # 绑定窗口大小变化事件，实现字体自动缩放
        self.root.bind('<Configure>', self.on_window_resize)
        
    def setup_styles(self):
        """设置 Material Design 样式。"""
        style = ttk.Style()
        
        # 使用 'clam' 主题作为基础（支持更多自定义）
        style.theme_use('clam')
        
        # 使用微软雅黑字体，确保中英文显示一致
        self.font_family = 'Microsoft YaHei UI'
        self.font_family_mono = 'Consolas'
        
        # Frame 样式
        style.configure('TFrame', background=self.COLORS['background'])
        style.configure('Card.TFrame', background=self.COLORS['surface'])
        
        # LabelFrame 样式（卡片效果）
        style.configure('Card.TLabelframe',
                       background=self.COLORS['surface'],
                       bordercolor=self.COLORS['primary'],
                       relief='flat')
        style.configure('Card.TLabelframe.Label',
                       background=self.COLORS['surface'],
                       foreground=self.COLORS['primary'],
                       font=(self.font_family, 11, 'bold'))
        
        # Label 样式
        style.configure('TLabel',
                       background=self.COLORS['background'],
                       foreground=self.COLORS['on_background'],
                       font=(self.font_family, 10))
        style.configure('Title.TLabel',
                       background=self.COLORS['background'],
                       foreground=self.COLORS['primary'],
                       font=(self.font_family, 16, 'bold'))
        style.configure('Desc.TLabel',
                       background=self.COLORS['background'],
                       foreground=self.COLORS['on_surface_secondary'],
                       font=(self.font_family, 10))
        style.configure('Card.TLabel',
                       background=self.COLORS['surface'],
                       foreground=self.COLORS['on_surface'],
                       font=(self.font_family, 10))
        style.configure('Note.TLabel',
                       background=self.COLORS['surface'],
                       foreground=self.COLORS['on_surface_secondary'],
                       font=(self.font_family, 9))
        style.configure('Stats.TLabel',
                       background=self.COLORS['background'],
                       foreground=self.COLORS['secondary'],
                       font=(self.font_family, 11, 'bold'))
        
        # Entry 样式
        style.configure('TEntry',
                       fieldbackground=self.COLORS['surface_light'],
                       foreground=self.COLORS['on_surface'],
                       insertcolor=self.COLORS['primary'],
                       bordercolor=self.COLORS['surface_light'],
                       lightcolor=self.COLORS['surface_light'],
                       darkcolor=self.COLORS['surface_light'],
                       padding=8)
        style.map('TEntry',
                 fieldbackground=[('disabled', self.COLORS['surface'])],
                 foreground=[('disabled', self.COLORS['on_surface_secondary'])])
        
        # Button 样式（Material Design 风格）
        style.configure('TButton',
                       background=self.COLORS['primary'],
                       foreground=self.COLORS['on_background'],
                       bordercolor=self.COLORS['primary'],
                       lightcolor=self.COLORS['primary'],
                       darkcolor=self.COLORS['primary_variant'],
                       font=(self.font_family, 10, 'bold'),
                       padding=(16, 8))
        style.configure('Secondary.TButton',
                       background=self.COLORS['surface_light'],
                       foreground=self.COLORS['on_surface'],
                       bordercolor=self.COLORS['surface_light'],
                       font=(self.font_family, 10),
                       padding=(16, 8))
        style.map('TButton',
                 background=[('active', self.COLORS['primary_variant']),
                            ('disabled', self.COLORS['surface'])],
                 foreground=[('disabled', self.COLORS['on_surface_secondary'])])
        style.map('Secondary.TButton',
                 background=[('active', self.COLORS['surface'])])
        
        # Checkbutton 样式
        style.configure('TCheckbutton',
                       background=self.COLORS['surface'],
                       foreground=self.COLORS['on_surface'],
                       font=(self.font_family, 10),
                       padding=8)
        style.map('TCheckbutton',
                 background=[('active', self.COLORS['surface'])])
        
        # Combobox 样式
        style.configure('TCombobox',
                       fieldbackground=self.COLORS['surface_light'],
                       background=self.COLORS['surface_light'],
                       foreground=self.COLORS['on_surface'],
                       arrowcolor=self.COLORS['primary'],
                       bordercolor=self.COLORS['surface_light'],
                       lightcolor=self.COLORS['surface_light'],
                       darkcolor=self.COLORS['surface_light'],
                       padding=8)
        style.map('TCombobox',
                 fieldbackground=[('disabled', self.COLORS['surface'])],
                 foreground=[('disabled', self.COLORS['on_surface_secondary'])],
                 background=[('disabled', self.COLORS['surface'])])
        
        # Progressbar 样式
        style.configure('TProgressbar',
                       background=self.COLORS['primary'],
                       troughcolor=self.COLORS['surface_light'],
                       bordercolor=self.COLORS['surface_light'],
                       lightcolor=self.COLORS['primary'],
                       darkcolor=self.COLORS['primary_variant'])
        
    def setup_ui(self):
        """设置 UI 组件 - Material Design 风格（响应式布局）。"""
        # 主框架 - 使用 grid 实现响应式布局
        main_frame = ttk.Frame(self.root, style='TFrame', padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 配置主框架的列权重（使内容可以水平扩展）
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)
        
        # 标题区域
        title_frame = ttk.Frame(main_frame, style='TFrame')
        title_frame.pack(fill=tk.X, pady=(0, 10))
        
        title_label = ttk.Label(title_frame, text="Ambisonics WAV Fixer",
                                style='Title.TLabel')
        title_label.pack(anchor=tk.CENTER)
        
        # 说明
        desc_label = ttk.Label(main_frame,
                               text="为 Ambisonics WAV 文件添加 iXML/bext 元数据，支持 FOA 到 7OA 全阶数",
                               style='Desc.TLabel', justify=tk.CENTER)
        desc_label.pack(pady=(0, 15), fill=tk.X)
        
        # 输入文件夹卡片
        input_frame = ttk.LabelFrame(main_frame, text="输入文件夹",
                                     style='Card.TLabelframe', padding="10")
        input_frame.pack(fill=tk.X, pady=(0, 8))
        
        input_inner = ttk.Frame(input_frame, style='Card.TFrame')
        input_inner.pack(fill=tk.X)
        input_inner.grid_columnconfigure(0, weight=1)  # Entry 扩展
        
        self.input_path = tk.StringVar()
        input_entry = ttk.Entry(input_inner, textvariable=self.input_path,
                               font=(self.font_family, 10))
        input_entry.grid(row=0, column=0, sticky='ew', padx=(0, 10))
        
        input_btn = ttk.Button(input_inner, text="浏览",
                              command=self.select_input_folder, width=8)
        input_btn.grid(row=0, column=1, sticky='e')
        
        # 输出文件夹卡片
        output_frame = ttk.LabelFrame(main_frame, text="输出文件夹",
                                      style='Card.TLabelframe', padding="10")
        output_frame.pack(fill=tk.X, pady=(0, 8))
        
        output_inner = ttk.Frame(output_frame, style='Card.TFrame')
        output_inner.pack(fill=tk.X)
        output_inner.grid_columnconfigure(0, weight=1)  # Entry 扩展
        
        self.output_path = tk.StringVar()
        self.output_entry = ttk.Entry(output_inner, textvariable=self.output_path,
                                       font=(self.font_family, 10))
        self.output_entry.grid(row=0, column=0, sticky='ew', padx=(0, 10))
        
        self.output_btn = ttk.Button(output_inner, text="浏览",
                                      command=self.select_output_folder, width=8)
        self.output_btn.grid(row=0, column=1, sticky='e')
        
        # 原地修改勾选框
        inplace_frame = ttk.Frame(output_frame, style='Card.TFrame')
        inplace_frame.pack(fill=tk.X, pady=(8, 0))
        
        self.inplace_var = tk.BooleanVar(value=False)
        self.inplace_check = ttk.Checkbutton(inplace_frame,
                                              text="原地修改（覆盖原文件）",
                                              variable=self.inplace_var,
                                              command=self.on_inplace_toggle,
                                              style='TCheckbutton')
        self.inplace_check.pack(side=tk.LEFT)
        
        # 打开输出文件夹按钮
        self.open_folder_btn = ttk.Button(inplace_frame, text="打开输出文件夹",
                                          command=self.open_output_folder, width=14,
                                          style='Secondary.TButton')
        self.open_folder_btn.pack(side=tk.RIGHT)
        
        # 通道顺序选择卡片
        channel_frame = ttk.LabelFrame(main_frame, text="通道顺序设置",
                                       style='Card.TLabelframe', padding="10")
        channel_frame.pack(fill=tk.X, pady=(0, 8))
        
        channel_inner = ttk.Frame(channel_frame, style='Card.TFrame')
        channel_inner.pack(fill=tk.X)
        channel_inner.grid_columnconfigure(0, weight=1)
        
        # 通道顺序下拉菜单
        self.channel_order_var = tk.StringVar(value="AmbiX")
        
        # 创建下拉菜单选项：AmbiX 和 FuMa 两个父级
        channel_options = ["AmbiX", "FuMa"]
        
        channel_label = ttk.Label(channel_inner, text="通道顺序：",
                                  style='Card.TLabel')
        channel_label.grid(row=0, column=0, sticky='w', padx=(0, 10))
        
        self.channel_combo = ttk.Combobox(channel_inner,
                                          textvariable=self.channel_order_var,
                                          values=channel_options,
                                          state='readonly',
                                          width=15,
                                          font=(self.font_family, 10))
        self.channel_combo.grid(row=0, column=1, sticky='w')
        
        # 说明文字
        channel_note = ttk.Label(channel_frame,
                                text="AmbiX 使用 ACN 通道排序，FuMa 使用传统 Furse-Malham 排序",
                                style='Note.TLabel')
        channel_note.pack(anchor=tk.W, pady=(8, 0))
        
        # 处理按钮区域
        button_frame = ttk.Frame(main_frame, style='TFrame')
        button_frame.pack(fill=tk.X, pady=15)
        
        self.process_btn = ttk.Button(button_frame, text="开始处理",
                                      command=self.start_processing, width=12)
        self.process_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.clear_btn = ttk.Button(button_frame, text="清空日志",
                                    command=self.clear_log, width=10,
                                    style='Secondary.TButton')
        self.clear_btn.pack(side=tk.LEFT)
        
        # 进度条 - 移除固定长度
        self.progress = ttk.Progressbar(main_frame, mode='determinate',
                                        style='TProgressbar')
        self.progress.pack(fill=tk.X, pady=(0, 8))
        
        # 结果显示区域卡片 - 使用 expand=True 使其可以垂直扩展
        result_frame = ttk.LabelFrame(main_frame, text="处理结果",
                                       style='Card.TLabelframe', padding="10")
        result_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        
        # 创建带深色背景的 ScrolledText - 移除固定高度和宽度
        self.log_text = scrolledtext.ScrolledText(
            result_frame,
            height=8,  # 最小高度
            bg=self.COLORS['surface_light'],
            fg=self.COLORS['on_surface'],
            insertbackground=self.COLORS['primary'],
            selectbackground=self.COLORS['primary'],
            selectforeground=self.COLORS['on_background'],
            font=(self.font_family_mono, 10),
            relief='flat',
            padx=10,
            pady=10,
            wrap=tk.WORD  # 自动换行
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # 配置文本颜色（Material Design 风格）
        self.log_text.tag_config('success',
                                foreground=self.COLORS['success'],
                                font=(self.font_family_mono, 10, 'bold'))
        self.log_text.tag_config('skipped',
                                foreground=self.COLORS['warning'])
        self.log_text.tag_config('error',
                                foreground=self.COLORS['error'],
                                font=(self.font_family_mono, 10, 'bold'))
        self.log_text.tag_config('info',
                                foreground=self.COLORS['info'])
        self.log_text.tag_config('header',
                                foreground=self.COLORS['primary'],
                                font=(self.font_family_mono, 11, 'bold'))
        
        # 统计标签
        self.stats_label = ttk.Label(main_frame, text="等待处理...",
                                     style='Stats.TLabel')
        self.stats_label.pack(pady=5)
    
    def select_input_folder(self):
        """选择输入文件夹。"""
        folder = filedialog.askdirectory(title="选择包含 WAV 文件的输入文件夹")
        if folder:
            self.input_path.set(folder)
    
    def select_output_folder(self):
        """选择输出文件夹。"""
        folder = filedialog.askdirectory(title="选择输出文件夹")
        if folder:
            self.output_path.set(folder)
            self.last_output_dir = folder
    
    def on_inplace_toggle(self):
        """原地修改勾选状态改变。"""
        if self.inplace_var.get():
            self.output_path.set("")
            self.output_entry.config(state='disabled')
            self.output_btn.config(state='disabled')
        else:
            self.output_entry.config(state='normal')
            self.output_btn.config(state='normal')
    
    def open_output_folder(self):
        """打开输出文件夹。"""
        output_dir = self.output_path.get() if not self.inplace_var.get() else self.input_path.get()
        
        if output_dir and os.path.isdir(output_dir):
            self.last_output_dir = output_dir
            # Windows 下打开文件夹
            if sys.platform == 'win32':
                os.startfile(output_dir)
            elif sys.platform == 'darwin':  # macOS
                subprocess.run(['open', output_dir])
            else:  # Linux
                subprocess.run(['xdg-open', output_dir])
        elif self.last_output_dir and os.path.isdir(self.last_output_dir):
            if sys.platform == 'win32':
                os.startfile(self.last_output_dir)
            elif sys.platform == 'darwin':
                subprocess.run(['open', self.last_output_dir])
            else:
                subprocess.run(['xdg-open', self.last_output_dir])
        else:
            self.log("请先选择输出文件夹或处理文件！", 'error')
    
    def log(self, message, tag='info'):
        """添加日志消息。"""
        self.log_text.insert(tk.END, message + '\n', tag)
        self.log_text.see(tk.END)
    
    def clear_log(self):
        """清空日志。"""
        self.log_text.delete(1.0, tk.END)
    
    def start_processing(self):
        """开始处理文件。"""
        input_dir = self.input_path.get()
        
        if not input_dir:
            self.log("请选择输入文件夹！", 'error')
            return
        
        if not os.path.isdir(input_dir):
            self.log(f"输入目录不存在: {input_dir}", 'error')
            return
        
        in_place = self.inplace_var.get()
        output_dir = self.output_path.get() if not in_place else None
        
        if not in_place and not output_dir:
            self.log("请选择输出文件夹或勾选原地修改！", 'error')
            return
        
        # 获取通道顺序选择
        channel_order = self.channel_order_var.get()
        
        # 记录输出目录
        if output_dir:
            self.last_output_dir = output_dir
        elif in_place:
            self.last_output_dir = input_dir
        
        # 禁用按钮
        self.process_btn.config(state='disabled')
        self.clear_btn.config(state='disabled')
        self.open_folder_btn.config(state='disabled')
        
        # 在线程中处理
        thread = threading.Thread(target=self.process_files,
                                  args=(input_dir, output_dir, in_place, channel_order))
        thread.start()
    
    def process_files(self, input_dir, output_dir, in_place, channel_order='AmbiX'):
        """处理文件（在后台线程中运行）。"""
        try:
            # 查找 WAV 文件
            input_path = Path(input_dir)
            wav_files = list(input_path.glob('*.wav')) + list(input_path.glob('*.WAV'))
            
            if not wav_files:
                self.log("未找到 WAV 文件！", 'error')
                self.finish_processing(0, 0, 0)
                return
            
            total = len(wav_files)
            self.log(f"找到 {total} 个 WAV 文件 (通道顺序: {channel_order})", 'header')
            self.log("=" * 50, 'info')
            
            # 设置进度条
            self.progress['maximum'] = total
            self.progress['value'] = 0
            
            success_count = 0
            skipped_count = 0
            error_count = 0
            
            for i, wav_file in enumerate(wav_files, 1):
                filename = wav_file.name
                
                # 更新进度
                self.progress['value'] = i
                self.root.update_idletasks()
                
                # 确定输出路径
                if in_place:
                    output_path = None
                elif output_dir:
                    output_path = os.path.join(output_dir, filename)
                else:
                    output_path = None
                
                # 处理文件
                status, message = process_wav_file(str(wav_file), output_path, in_place,
                                                  lambda m: self.log(m, 'info'), channel_order)
                
                # 输出结果
                if status == 'SUCCESS':
                    self.log(f"[{i}/{total}] {filename}", 'info')
                    self.log(f"  ✓ SUCCESS: {message}", 'success')
                    success_count += 1
                elif status == 'SKIPPED':
                    self.log(f"[{i}/{total}] {filename}", 'info')
                    self.log(f"  ○ SKIPPED: {message}", 'skipped')
                    skipped_count += 1
                else:
                    self.log(f"[{i}/{total}] {filename}", 'info')
                    self.log(f"  ✗ ERROR: {message}", 'error')
                    error_count += 1
            
            self.log("=" * 50, 'info')
            self.finish_processing(success_count, skipped_count, error_count)
        
        except Exception as e:
            self.log(f"处理出错: {e}", 'error')
            self.finish_processing(0, 0, 0)
    
    def finish_processing(self, success, skipped, errors):
        """处理完成后的清理工作。"""
        self.stats_label.config(text=f"完成: ✓ {success} 成功 | ○ {skipped} 跳过 | ✗ {errors} 错误")
        
        # 重新启用按钮
        self.process_btn.config(state='normal')
        self.clear_btn.config(state='normal')
        self.open_folder_btn.config(state='normal')
        
        self.root.update_idletasks()
    
    def on_window_resize(self, event):
        """窗口大小变化时自动缩放字体。"""
        # 防止递归调用
        if event.widget != self.root:
            return
        
        # 获取当前窗口大小
        current_width = self.root.winfo_width()
        current_height = self.root.winfo_height()
        
        # 计算缩放比例（基于宽度和高度的平均值）
        width_ratio = current_width / self.base_window_width
        height_ratio = current_height / self.base_window_height
        scale_ratio = (width_ratio + height_ratio) / 2
        
        # 限制缩放范围（最小0.8，最大2.0）
        scale_ratio = max(0.8, min(2.0, scale_ratio))
        
        # 计算新的字体大小
        new_font_size = int(self.base_font_size * scale_ratio)
        
        # 更新 ttk 样式中的字体大小
        style = ttk.Style()
        
        # 更新各种样式字体（使用微软雅黑）
        style.configure('TLabel', font=(self.font_family, new_font_size))
        style.configure('Title.TLabel', font=(self.font_family, int(new_font_size * 1.5), 'bold'))
        style.configure('Desc.TLabel', font=(self.font_family, int(new_font_size * 0.9)))
        style.configure('Note.TLabel', font=(self.font_family, int(new_font_size * 0.85)))
        style.configure('Stats.TLabel', font=(self.font_family, int(new_font_size * 1.1), 'bold'))
        style.configure('TButton', font=(self.font_family, new_font_size))
        style.configure('Secondary.TButton', font=(self.font_family, new_font_size))
        style.configure('TCheckbutton', font=(self.font_family, new_font_size))
        style.configure('Card.TLabelframe.Label', font=(self.font_family, int(new_font_size * 1.1), 'bold'))
        
        # 更新 Entry 字体
        try:
            new_entry_font = (self.font_family, new_font_size)
            if hasattr(self, 'output_entry'):
                self.output_entry.config(font=new_entry_font)
        except Exception:
            pass
        
        # 更新日志文本字体
        try:
            if hasattr(self, 'log_text'):
                log_font_size = max(8, int(new_font_size * 0.95))
                self.log_text.config(font=(self.font_family_mono, log_font_size))
                # 更新 tag 字体
                self.log_text.tag_config('success', font=(self.font_family_mono, log_font_size, 'bold'))
                self.log_text.tag_config('error', font=(self.font_family_mono, log_font_size, 'bold'))
                self.log_text.tag_config('header', font=(self.font_family_mono, int(log_font_size * 1.1), 'bold'))
        except Exception:
            pass
    
    def run(self):
        """运行 GUI。"""
        self.root.mainloop()


# ============================================================================
# 主入口
# ============================================================================

def main():
    """主入口函数。"""
    app = AmbisonicsFixerGUI()
    app.run()


if __name__ == '__main__':
    main()
// Path: frontend/src/hooks/useTranscript.ts

import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import type { ChunkData, TranscriptSegment } from '../types';

const API_BASE = `http://localhost:8001/api`;

export const useTranscript = () => {
  const [chunks, setChunks] = useState<string[]>([]);
  const [selectedChunk, setSelectedChunk] = useState<string>('');
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [speakerMap, setSpeakerMap] = useState<Record<string, string>>({});
  const [videoOffset, setVideoOffset] = useState<number>(0);
  const [mediaFileName, setMediaFileName] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);

  // 初始化載入 chunk 列表
  useEffect(() => {
    axios.get(`${API_BASE}/temp/chunks`).then(res => {
      if (res.data.files) {
        setChunks(res.data.files);
        if (res.data.files.length > 0) setSelectedChunk(res.data.files[0]);
      }
    });
  }, []);

  // 當選擇的 Chunk 改變時，載入詳細資料
  useEffect(() => {
    if (!selectedChunk) return;
    setLoading(true);
    axios.get<ChunkData>(`${API_BASE}/temp/chunk/${selectedChunk}`)
      .then(res => {
        const data = res.data;
        setVideoOffset(data.video_offset || 0);
        if (data.media_file) setMediaFileName(data.media_file);
        
        if (Array.isArray(data)) {
           setSegments(data);
           setSpeakerMap({});
        } else {
           setSegments(data.segments || []);
           setSpeakerMap(data.speaker_mapping || {});
        }
        setHasUnsavedChanges(false);
      })
      .finally(() => setLoading(false));
  }, [selectedChunk]);

  // 修改文字
  const updateText = useCallback((id: number, newText: string) => {
    setSegments(prev => prev.map(seg => 
      seg.sentence_id === id ? { ...seg, text: newText } : seg
    ));
    setHasUnsavedChanges(true);
  }, []);

  // 更新時間
  const updateSegmentTime = useCallback((index: number, newRelativeStart: number) => {
    setSegments(prev => {
        const newSegments = [...prev];
        newSegments[index] = { ...newSegments[index], start: newRelativeStart };
        return newSegments;
    });
    setHasUnsavedChanges(true);
  }, []);

  // 更新語者
  const updateSpeaker = useCallback((index: number, newSpeakerId: string) => {
    setSegments(prev => {
        const copy = [...prev];
        copy[index] = { ...copy[index], speaker: newSpeakerId };
        return copy;
    });
    setHasUnsavedChanges(true);
  }, []);

  const renameSpeaker = useCallback((originalId: string, newName: string) => {
    setSpeakerMap(prev => ({ ...prev, [originalId]: newName }));
    setHasUnsavedChanges(true);
  }, []);

  const save = async () => {
    if (!selectedChunk) return;
    await axios.post(`${API_BASE}/temp/save`, {
      filename: selectedChunk,
      speaker_mapping: speakerMap,
      segments: segments
    });
    setHasUnsavedChanges(false);
  };

  return {
    chunks, selectedChunk, setSelectedChunk,
    segments, speakerMap, videoOffset, mediaFileName, setMediaFileName,
    loading, hasUnsavedChanges,
    updateText, updateSegmentTime, updateSpeaker, renameSpeaker, save
  };
};
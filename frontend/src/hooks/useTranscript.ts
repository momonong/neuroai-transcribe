import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import type { ChunkData, TranscriptSegment, ChunkTimepoint } from '../types';

const API_BASE = `/api`;

export const useTranscript = () => {
  const [chunks, setChunks] = useState<string[]>([]);
  const [selectedChunk, setSelectedChunk] = useState<string>('');
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [speakerMap, setSpeakerMap] = useState<Record<string, string>>({});
  const [videoOffset, setVideoOffset] = useState<number>(0);
  const [mediaFileName, setMediaFileName] = useState<string>('');
  const [chunkTimepoints, setChunkTimepoints] = useState<ChunkTimepoint[]>([]);
  const [fileType, setFileType] = useState<'flagged' | 'edited' | 'original'>('original');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [existingTesters, setExistingTesters] = useState<string[]>([]); // ★ 案例清單

  // 1. 載入列表
  const fetchChunks = useCallback(() => {
    axios.get(`${API_BASE}/temp/chunks`)
      .then(res => {
        if (res.data.files) {
          setChunks(res.data.files);
          if (!selectedChunk && res.data.files.length > 0) {
             setSelectedChunk(res.data.files[0]);
          }
        }
      })
      .catch(err => console.error(err));
  }, [selectedChunk]);

  // ★ 新增：取得案例名單
  const fetchTesters = useCallback(() => {
      axios.get(`${API_BASE}/testers`)
        .then(res => setExistingTesters(res.data))
        .catch(console.error);
  }, []);

  useEffect(() => {
    fetchChunks();
    fetchTesters();
  }, [fetchChunks, fetchTesters]);

  // 2. 載入詳細資料
  useEffect(() => {
    if (!selectedChunk) return;
    setLoading(true);
    setError(null);
    
    axios.get<ChunkData>(`${API_BASE}/temp/chunk/${selectedChunk}`)
      .then(res => {
        const data = res.data;
        setVideoOffset(data.video_offset || 0);
        if (data.media_file) setMediaFileName(data.media_file);
        if (data.chunk_timepoints) setChunkTimepoints(data.chunk_timepoints);
        if (data.file_type) setFileType(data.file_type);
        
        if (Array.isArray(data)) {
           setSegments(data);
           setSpeakerMap({});
        } else {
           setSegments(data.segments || []);
           setSpeakerMap(data.speaker_mapping || {});
        }
        setHasUnsavedChanges(false);
      })
      .catch(err => {
        console.error(err);
        setError("讀取資料失敗");
      })
      .finally(() => setLoading(false));
  }, [selectedChunk]);

  // --- 編輯功能 ---

  const updateText = useCallback((id: number, newText: string) => {
    setSegments(prev => prev.map(seg => 
      seg.sentence_id === id ? { ...seg, text: newText } : seg
    ));
    setHasUnsavedChanges(true);
  }, []);

  const updateSegmentTime = useCallback((index: number, newRelativeStart: number) => {
    setSegments(prev => {
        const newSegments = [...prev];
        newSegments[index] = { ...newSegments[index], start: newRelativeStart };
        return newSegments;
    });
    setHasUnsavedChanges(true);
  }, []);

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

  // ★★★ 新增：刪除功能 ★★★
  const deleteSegment = useCallback((index: number) => {
    setSegments(prev => {
        const newSegs = [...prev];
        newSegs.splice(index, 1);
        return newSegs;
    });
    setHasUnsavedChanges(true);
  }, []);

  // ★★★ 新增：插入功能 ★★★
  const addSegment = useCallback((index: number) => {
    setSegments(prev => {
        const newSegs = [...prev];
        const currentSeg = newSegs[index];
        const newStart = currentSeg ? currentSeg.end : 0;
        
        const newSegment: TranscriptSegment = {
            sentence_id: Date.now(),
            start: newStart,
            end: newStart + 2.0,
            text: "新對話...",
            speaker: currentSeg ? currentSeg.speaker : "SPEAKER_00",
            status: "new",
            verification_score: 1.0,
            needs_review: false,
            review_reason: null
        };
        newSegs.splice(index + 1, 0, newSegment);
        return newSegs;
    });
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

  // ★★★ 新增：上傳功能 ★★★
  const uploadVideo = async (file: File, caseName: string) => {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('case_name', caseName);
      
      await axios.post(`${API_BASE}/upload`, formData, {
          headers: { 'Content-Type': 'multipart/form-data' }
      });
      fetchChunks(); 
      fetchTesters();
  };

  return {
    chunks, selectedChunk, setSelectedChunk,
    segments, speakerMap, videoOffset, mediaFileName, setMediaFileName,
    chunkTimepoints, fileType,
    loading, error, hasUnsavedChanges, existingTesters, // ★ 記得匯出 existingTesters (現在是案例清單)
    updateText, updateSegmentTime, updateSpeaker, renameSpeaker, save,
    deleteSegment, addSegment, uploadVideo, fetchTesters // ★ 記得匯出這些 function
  };
};
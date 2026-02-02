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
  const [existingTesters, setExistingTesters] = useState<string[]>([]);

  // 1. Load List
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

  const fetchTesters = useCallback(() => {
      axios.get(`${API_BASE}/cases`)
        .then(res => setExistingTesters(res.data))
        .catch(console.error);
  }, []);

  useEffect(() => {
    fetchChunks();
    fetchTesters();
  }, [fetchChunks, fetchTesters]);

  // 2. Load Details
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
        setError("Failed to load data");
      })
      .finally(() => setLoading(false));
  }, [selectedChunk]);

  // --- Edit Functions ---

  // Generic update function
  const updateSegmentFull = useCallback((index: number, updatedFields: Partial<TranscriptSegment>) => {
    setSegments(prev => {
      const newSegs = [...prev];
      newSegs[index] = { ...newSegs[index], ...updatedFields };
      return newSegs;
    });
    setHasUnsavedChanges(true);
  }, []);

  // Stable function for resolving flags (Accept/Ignore)
  // Using functional update (prev => ...) prevents dependency on 'segments', fixing lag.
  const resolveFlag = useCallback((index: number, action: 'accept' | 'ignore') => {
    setSegments(prev => {
      const newSegs = [...prev];
      const targetSegment = newSegs[index];
      if (!targetSegment) return prev;

      let newText = targetSegment.text;
      
      if (action === 'accept' && targetSegment.suggested_correction) {
        newText = targetSegment.suggested_correction;
      }

      // Update object: set new text and clear review flags
      newSegs[index] = {
        ...targetSegment,
        text: newText,
        needs_review: false,
        review_reason: null,
        suggested_correction: null
      };
      return newSegs;
    });
    setHasUnsavedChanges(true);
  }, []);

  const updateText = useCallback((index: number, newText: string) => {
    updateSegmentFull(index, { text: newText });
  }, [updateSegmentFull]);

  const updateSegmentTime = useCallback((index: number, newRelativeStart: number) => {
    updateSegmentFull(index, { start: newRelativeStart });
  }, [updateSegmentFull]);

  const updateSpeaker = useCallback((index: number, newSpeakerId: string) => {
    updateSegmentFull(index, { speaker: newSpeakerId });
  }, [updateSegmentFull]);

  const renameSpeaker = useCallback((originalId: string, newName: string) => {
    setSpeakerMap(prev => ({ ...prev, [originalId]: newName }));
    setHasUnsavedChanges(true);
  }, []);

  const deleteSegment = useCallback((index: number) => {
    setSegments(prev => {
      const newSegs = [...prev];
      newSegs.splice(index, 1);
      return newSegs;
    });
    setHasUnsavedChanges(true);
  }, []);

  const addSegment = useCallback((index: number) => {
    setSegments(prev => {
      const newSegs = [...prev];
      const currentSeg = newSegs[index];
      const newStart = currentSeg ? currentSeg.end : 0;
      
      const newSegment: TranscriptSegment = {
          sentence_id: Date.now(),
          start: newStart,
          end: newStart + 2.0,
          text: "",
          speaker: currentSeg ? currentSeg.speaker : "SPEAKER_00",
          status: "new",
          verification_score: 1.0,
          needs_review: false,
          review_reason: null,
          suggested_correction: null
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
    loading, error, hasUnsavedChanges, existingTesters,
    
    updateText, 
    updateSegmentTime, 
    updateSpeaker, 
    renameSpeaker, 
    save,
    deleteSegment, 
    addSegment, 
    uploadVideo, 
    fetchTesters,
    updateSegmentFull,
    resolveFlag // Exporting the stable resolve function
  };
};
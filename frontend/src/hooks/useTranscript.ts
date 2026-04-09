import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import type { ChunkData, TranscriptSegment, ChunkTimepoint } from '../types';

const API_BASE = `/api`;

export type SegmentReinferResponse = {
  ok: boolean;
  text: string | null;
  message: string;
};

export const useTranscript = (projectId: number | null) => {
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
  const [reinferLoadingIndex, setReinferLoadingIndex] = useState<number | null>(null);

  const fetchChunks = useCallback(() => {
    if (projectId == null) {
      setChunks([]);
      return;
    }
    axios
      .get(`${API_BASE}/temp/chunks`, { params: { project_id: projectId } })
      .then((res) => {
        if (res.data.files) {
          const files: string[] = res.data.files;
          setChunks(files);
          setSelectedChunk((prev) => {
            if (prev && files.includes(prev)) return prev;
            const caseOf = (p: string) => p.replace(/\\/g, '/').split('/')[0] || '';
            const demoFiles = files.filter((f) => caseOf(f) === 'default_demo');
            const ordered =
              demoFiles.length > 0
                ? [...demoFiles, ...files.filter((f) => !demoFiles.includes(f))]
                : files;
            return ordered.length > 0 ? ordered[0] : '';
          });
        }
      })
      .catch((err) => console.error(err));
  }, [projectId]);

  const fetchTesters = useCallback(() => {
    if (projectId == null) {
      setExistingTesters([]);
      return;
    }
    axios
      .get<Array<{ case_name: string }>>(`${API_BASE}/cases`, { params: { project_id: projectId } })
      .then((res) => setExistingTesters(res.data.map((r) => r.case_name)))
      .catch(console.error);
  }, [projectId]);

  useEffect(() => {
    fetchChunks();
    fetchTesters();
  }, [fetchChunks, fetchTesters]);

  useEffect(() => {
    if (!selectedChunk) {
      setSegments([]);
      setSpeakerMap({});
      setChunkTimepoints([]);
      setVideoOffset(0);
      setFileType('original');
      setError(null);
      setLoading(false);
      setHasUnsavedChanges(false);
      return;
    }
    setLoading(true);
    setError(null);

    axios
      .get<ChunkData>(`${API_BASE}/temp/chunk/${selectedChunk}`)
      .then((res) => {
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
      .catch((err) => {
        console.error(err);
        setError('Failed to load data');
      })
      .finally(() => setLoading(false));
  }, [selectedChunk]);

  const updateSegmentFull = useCallback((index: number, updatedFields: Partial<TranscriptSegment>) => {
    setSegments((prev) => {
      const newSegs = [...prev];
      newSegs[index] = { ...newSegs[index], ...updatedFields };
      return newSegs;
    });
    setHasUnsavedChanges(true);
  }, []);

  const resolveFlag = useCallback((index: number, action: 'accept' | 'ignore') => {
    setSegments((prev) => {
      const newSegs = [...prev];
      const targetSegment = newSegs[index];
      if (!targetSegment) return prev;

      let newText = targetSegment.text;

      if (action === 'accept' && targetSegment.suggested_correction) {
        newText = targetSegment.suggested_correction;
      }

      newSegs[index] = {
        ...targetSegment,
        text: newText,
        needs_review: false,
        review_reason: null,
        suggested_correction: null,
      };
      return newSegs;
    });
    setHasUnsavedChanges(true);
  }, []);

  const updateText = useCallback(
    (index: number, newText: string) => {
      updateSegmentFull(index, { text: newText });
    },
    [updateSegmentFull]
  );

  const updateSegmentTime = useCallback(
    (index: number, newRelativeStart: number) => {
      updateSegmentFull(index, { start: newRelativeStart });
    },
    [updateSegmentFull]
  );

  const updateSegmentEndTime = useCallback(
    (index: number, newRelativeEnd: number) => {
      updateSegmentFull(index, { end: newRelativeEnd });
    },
    [updateSegmentFull]
  );

  const updateSpeaker = useCallback(
    (index: number, newSpeakerId: string) => {
      updateSegmentFull(index, { speaker: newSpeakerId });
    },
    [updateSegmentFull]
  );

  const renameSpeaker = useCallback((originalId: string, newName: string) => {
    setSpeakerMap((prev) => ({ ...prev, [originalId]: newName }));
    setHasUnsavedChanges(true);
  }, []);

  const deleteSegment = useCallback((index: number) => {
    setSegments((prev) => {
      const newSegs = [...prev];
      newSegs.splice(index, 1);
      return newSegs;
    });
    setHasUnsavedChanges(true);
  }, []);

  const addSegment = useCallback((index: number) => {
    setSegments((prev) => {
      const newSegs = [...prev];
      const currentSeg = newSegs[index];
      const newStart = currentSeg ? currentSeg.end : 0;

      const newSegment: TranscriptSegment = {
        sentence_id: Date.now(),
        start: newStart,
        end: newStart + 2.0,
        text: '',
        speaker: currentSeg ? currentSeg.speaker : 'SPEAKER_00',
        status: 'new',
        verification_score: 1.0,
        needs_review: false,
        review_reason: null,
        suggested_correction: null,
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
      segments: segments,
    });
    setHasUnsavedChanges(false);
  };

  const reinferSegment = useCallback(
    async (index: number): Promise<SegmentReinferResponse> => {
      if (!selectedChunk) {
        return { ok: false, text: null, message: '未選擇要編輯的 chunk' };
      }
      const seg = segments[index];
      if (!seg) {
        return { ok: false, text: null, message: '找不到該片段' };
      }
      if (seg.end <= seg.start) {
        return {
          ok: false,
          text: null,
          message: '結束時間必須大於開始時間，請先調整時間範圍',
        };
      }
      setReinferLoadingIndex(index);
      try {
        const { data } = await axios.post<SegmentReinferResponse>(`${API_BASE}/temp/reinfer-segment`, {
          filename: selectedChunk,
          start_sec: seg.start,
          end_sec: seg.end,
          sentence_id: seg.sentence_id,
        });
        if (data.text != null && String(data.text).trim() !== '') {
          updateText(index, String(data.text).trim());
        }
        return data;
      } catch (e: unknown) {
        const ax = e as { response?: { data?: { detail?: unknown } } };
        const d = ax.response?.data?.detail;
        const msg =
          typeof d === 'string'
            ? d
            : Array.isArray(d)
              ? JSON.stringify(d)
              : '重新辨識請求失敗';
        return { ok: false, text: null, message: msg };
      } finally {
        setReinferLoadingIndex(null);
      }
    },
    [selectedChunk, segments, updateText],
  );

  const uploadVideo = async (file: File, caseName: string, pid: number) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('case_name', caseName);
    formData.append('project_id', String(pid));

    await axios.post(`${API_BASE}/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    fetchChunks();
    fetchTesters();
  };

  return {
    chunks,
    selectedChunk,
    setSelectedChunk,
    segments,
    speakerMap,
    videoOffset,
    mediaFileName,
    setMediaFileName,
    chunkTimepoints,
    fileType,
    loading,
    error,
    hasUnsavedChanges,
    existingTesters,

    updateText,
    updateSegmentTime,
    updateSegmentEndTime,
    updateSpeaker,
    renameSpeaker,
    save,
    deleteSegment,
    addSegment,
    uploadVideo,
    fetchTesters,
    fetchChunks,
    updateSegmentFull,
    resolveFlag,
    reinferSegment,
    reinferLoadingIndex,
  };
};

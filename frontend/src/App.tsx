import { useEffect, useState, useRef, useMemo } from 'react';
import axios from 'axios';

// ★★★ 修正點：加上 'type' 關鍵字 ★★★
import type { SelectChangeEvent } from '@mui/material/Select';

import { 
  Box, Typography, Chip, Drawer, List, ListItem, ListItemText, 
  ListItemIcon, Divider, Button, TextField, Snackbar, 
  Alert, CircularProgress, Paper, IconButton, Tooltip,
  Menu, MenuItem, Dialog, DialogTitle, DialogContent, DialogActions,
  Select, FormControl, InputLabel 
} from '@mui/material';

import { 
  Save, PlayCircleFilled, Dashboard, 
  VideoLibrary, Person, Refresh, WarningAmber, Add, Edit, CheckCircle,
  Movie, AccessTime 
} from '@mui/icons-material';

// --- 設定區 ---
const API_PORT = 8001;
const API_BASE = `http://localhost:${API_PORT}/api`;
const STATIC_BASE = `http://localhost:${API_PORT}/static`; 

// --- 資料介面 ---
interface TranscriptSegment {
  start: number;
  end: number;
  speaker: string; 
  text: string;
  verification_score: number;
  status: string;
  sentence_id: number;
  needs_review: boolean;
  review_reason: string | null;
}

interface ChunkData {
  speaker_mapping: Record<string, string>;
  segments: TranscriptSegment[];
  media_file?: string;
  video_offset?: number;
}

interface VideoFile {
    path: string; 
    name: string; 
}

const formatTime = (seconds: number) => {
  if (isNaN(seconds)) return "00:00";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  const ms = Math.floor((seconds % 1) * 10); // 增加小數點顯示，方便微調
  return `${mins}:${secs.toString().padStart(2, '0')}.${ms}`;
};

function App() {
  const videoRef = useRef<HTMLVideoElement>(null);
  
  // --- Data State ---
  const [chunks, setChunks] = useState<string[]>([]);
  const [selectedChunk, setSelectedChunk] = useState<string>('');
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [speakerMap, setSpeakerMap] = useState<Record<string, string>>({}); 
  const [availableVideos, setAvailableVideos] = useState<VideoFile[]>([]); 
  const [mediaFileName, setMediaFileName] = useState<string>('');          
  const [videoOffset, setVideoOffset] = useState<number>(0);

  // --- UI State ---
  const [loading, setLoading] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null); 
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<{open: boolean, msg: string, type: 'success' | 'error' | 'info'}>({
    open: false, msg: '', type: 'info'
  });

  // --- Menu State ---
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const [activeSegmentIndex, setActiveSegmentIndex] = useState<number | null>(null);
  const [isNewSpeakerDialogOpen, setIsNewSpeakerDialogOpen] = useState(false);
  const [newSpeakerName, setNewSpeakerName] = useState("");

  useEffect(() => { 
      fetchChunkList(); 
      fetchVideoList(); 
  }, []);
  
  useEffect(() => { if (selectedChunk) fetchChunkData(selectedChunk); }, [selectedChunk]);

  const allSpeakers = useMemo(() => {
    const rawSpeakers = new Set(segments.map(seg => seg.speaker));
    Object.keys(speakerMap).forEach(k => rawSpeakers.add(k));
    return Array.from(rawSpeakers).sort();
  }, [segments, speakerMap]);

  // --- API Functions ---
  const fetchVideoList = () => {
      axios.get(`${API_BASE}/videos`)
        .then(res => setAvailableVideos(res.data))
        .catch(err => console.error("Failed to fetch videos", err));
  };

  const fetchChunkList = () => {
    axios.get(`${API_BASE}/temp/chunks`)
      .then(res => {
        if (res.data.files) {
            setChunks(res.data.files);
            if (res.data.files.length > 0 && !selectedChunk) setSelectedChunk(res.data.files[0]);
        }
      })
      .catch(err => console.error(err));
  };

  const fetchChunkData = (filename: string) => {
    setLoading(true);
    axios.get<ChunkData>(`${API_BASE}/temp/chunk/${filename}`)
      .then(res => {
        const data = res.data;
        if (!mediaFileName && data.media_file) {
            setMediaFileName(data.media_file);
        } else if (data.media_file && data.media_file !== mediaFileName) {
             if (mediaFileName === '') setMediaFileName(data.media_file);
        }
        setVideoOffset(data.video_offset || 0);
        if (Array.isArray(data)) {
           setSegments(data);
           setSpeakerMap({});
        } else {
           setSegments(data.segments || []);
           setSpeakerMap(data.speaker_mapping || {});
        }
        setHasUnsavedChanges(false);
        setEditingId(null);
        if (videoRef.current && (data.video_offset !== undefined)) {
            setTimeout(() => {
                if(videoRef.current) videoRef.current.currentTime = data.video_offset || 0;
            }, 200);
        }
      })
      .catch(err => {
        console.error(err);
        setToast({ open: true, msg: '讀取資料失敗', type: 'error' });
      })
      .finally(() => setLoading(false));
  };

  const handleSave = async () => {
    if (!selectedChunk) return;
    setSaving(true);
    const payload = {
        filename: selectedChunk,
        speaker_mapping: speakerMap,
        segments: segments
    };
    try {
      const res = await axios.post(`${API_BASE}/temp/save`, payload);
      setHasUnsavedChanges(false);
      setEditingId(null);
      const msg = res.data.new_filename ? `已另存為: ${res.data.new_filename}` : '存檔成功！';
      setToast({ open: true, msg: `✅ ${msg}`, type: 'success' });
      fetchChunkList();
    } catch (error: any) {
      setToast({ open: true, msg: `❌ 存檔失敗: ${error.message}`, type: 'error' });
    } finally {
      setSaving(false);
    }
  };

  // --- Handlers ---
  const handleVideoSelectChange = (event: SelectChangeEvent) => {
      setMediaFileName(event.target.value);
  };

  // ★★★ 新增：同步時間功能 ★★★
  const handleSyncTime = (index: number) => {
    if (!videoRef.current) return;
    
    // 1. 取得目前影片的絕對時間
    const currentAbsTime = videoRef.current.currentTime;
    
    // 2. 計算新的相對時間 (目前時間 - Offset)
    // 確保不會變成負數
    const newRelativeStart = Math.max(0, currentAbsTime - videoOffset);

    // 3. 更新 Segments
    setSegments(prev => {
        const newSegments = [...prev];
        newSegments[index] = { 
            ...newSegments[index], 
            start: newRelativeStart 
        };
        // 選用：是否要自動排序？如果不排序，順序可能會亂掉，但編輯體驗較直覺
        // newSegments.sort((a, b) => a.start - b.start); 
        return newSegments;
    });

    setHasUnsavedChanges(true);
    setToast({ open: true, msg: `已將時間點更新為 ${formatTime(currentAbsTime)}`, type: 'info' });
  };

  const handleSpeakerClick = (event: React.MouseEvent<HTMLElement>, index: number) => {
    setAnchorEl(event.currentTarget);
    setActiveSegmentIndex(index);
  };

  const handleSelectExistingSpeaker = (speakerId: string) => {
    if (activeSegmentIndex !== null) changeSegmentSpeaker(activeSegmentIndex, speakerId);
    setAnchorEl(null);
  };

  const handleOpenNewSpeakerDialog = () => {
    setAnchorEl(null);
    setNewSpeakerName("");
    setIsNewSpeakerDialogOpen(true);
  };

  const confirmNewSpeaker = () => {
    if (activeSegmentIndex !== null && newSpeakerName.trim()) changeSegmentSpeaker(activeSegmentIndex, newSpeakerName.trim());
    setIsNewSpeakerDialogOpen(false);
  };

  const changeSegmentSpeaker = (index: number, newSpeakerId: string) => {
    setSegments(prev => {
        const newSegments = [...prev];
        newSegments[index] = { ...newSegments[index], speaker: newSpeakerId };
        return newSegments;
    });
    setHasUnsavedChanges(true);
  };

  const handleSpeakerRename = (originalId: string, newName: string) => {
    setSpeakerMap(prev => ({ ...prev, [originalId]: newName }));
    setHasUnsavedChanges(true);
  };

  const handleTextChange = (id: number, newText: string) => {
    setSegments(prev => prev.map(seg => seg.sentence_id === id ? { ...seg, text: newText } : seg));
    setHasUnsavedChanges(true);
  };

  const handleJumpToTime = (segmentRelativeStart: number) => {
    if (videoRef.current) {
      const absoluteTime = videoOffset + segmentRelativeStart;
      videoRef.current.currentTime = absoluteTime;
      videoRef.current.play(); // 跳轉後自動播放，方便確認
    }
  };

  return (
    <Box sx={{ display: 'flex', height: '100vh', bgcolor: '#0f172a', color: '#e2e8f0', fontFamily: 'Inter, sans-serif' }}>
      
      {/* 側邊欄 */}
      <Drawer variant="permanent" sx={{ width: 260, flexShrink: 0, [`& .MuiDrawer-paper`]: { width: 260, bgcolor: '#1e293b', color: '#94a3b8', borderRight: '1px solid #334155' } }}>
        <Box sx={{ p: 2, display: 'flex', alignItems: 'center', gap: 1, color: '#38bdf8' }}>
            <Dashboard /><Typography variant="subtitle1" fontWeight="bold">NeuroAI Editor</Typography>
        </Box>
        <List sx={{ px: 1, overflowY: 'auto', flex: 1 }}>
          {chunks.map((filename) => (
            <ListItem button key={filename} selected={selectedChunk === filename} onClick={() => setSelectedChunk(filename)} sx={{ borderRadius: 1, mb: 0.5, '&.Mui-selected': { bgcolor: '#2563eb', color: 'white' } }}>
              <ListItemIcon sx={{ color: 'inherit', minWidth: 32 }}><VideoLibrary fontSize="small" /></ListItemIcon>
              <ListItemText primary={filename.replace("_flagged_for_human.json", "").replace("_corrected.json", " (已修正)")} primaryTypographyProps={{ fontSize: '0.8rem', noWrap: true }} />
            </ListItem>
          ))}
        </List>
      </Drawer>

      {/* 主內容 */}
      <Box component="main" sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
        
        {/* Top Bar */}
        <Paper square elevation={0} sx={{ height: 64, px: 3, display: 'flex', alignItems: 'center', justifyContent: 'space-between', bgcolor: '#1e293b', borderBottom: '1px solid #334155' }}>
            <Box sx={{ display: 'flex', gap: 2, overflowX: 'auto', alignItems: 'center', flex: 1, mr: 4 }}>
                <Typography variant="caption" sx={{ color: '#64748b', fontWeight: 'bold' }}>ALIAS:</Typography>
                {allSpeakers.map(spk => (
                    <Box key={spk} sx={{ display: 'flex', alignItems: 'center', bgcolor: '#334155', borderRadius: 8, px: 1.5, py: 0.5, border: '1px solid #475569' }}>
                        <Typography variant="caption" sx={{ color: '#94a3b8', mr: 1 }}>{spk}</Typography>
                        <input value={speakerMap[spk] || ''} onChange={(e) => handleSpeakerRename(spk, e.target.value)} placeholder="別名" style={{ background: 'transparent', border: 'none', color: '#fff', fontSize: '0.85rem', width: 60, outline: 'none', fontWeight: 'bold' }} />
                    </Box>
                ))}
            </Box>
            <Button variant="contained" color={hasUnsavedChanges ? "warning" : "primary"} startIcon={saving ? <CircularProgress size={20} color="inherit"/> : <Save />} onClick={handleSave} disabled={!hasUnsavedChanges || saving}>
                {saving ? "Saving..." : hasUnsavedChanges ? "Save Changes" : "All Saved"}
            </Button>
        </Paper>

        <Box sx={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
            
            {/* 左側：影片區 */}
            <Box sx={{ width: '45%', bgcolor: '#000', display: 'flex', flexDirection: 'column', alignItems: 'center', position: 'relative' }}>
                {/* 影片選擇器 */}
                <Box sx={{ width: '100%', p: 1, bgcolor: '#0f172a', borderBottom: '1px solid #334155', display: 'flex', alignItems: 'center', gap: 2 }}>
                    <Movie sx={{ color: '#94a3b8' }} />
                    <FormControl size="small" fullWidth sx={{ bgcolor: '#1e293b', borderRadius: 1 }}>
                        <InputLabel id="video-select-label" sx={{ color: '#94a3b8' }}>選擇影片來源 (Source Video)</InputLabel>
                        <Select
                            labelId="video-select-label"
                            value={mediaFileName}
                            label="選擇影片來源 (Source Video)"
                            onChange={handleVideoSelectChange}
                            sx={{ color: 'white', '& .MuiOutlinedInput-notchedOutline': { borderColor: 'transparent' } }}
                        >
                            {availableVideos.length === 0 && <MenuItem disabled>找不到任何影片</MenuItem>}
                            {availableVideos.map((v) => (
                                <MenuItem key={v.path} value={v.path}>
                                    {v.name} <span style={{opacity: 0.5, fontSize: '0.8em', marginLeft: 8}}>({v.path})</span>
                                </MenuItem>
                            ))}
                        </Select>
                    </FormControl>
                </Box>

                <Box sx={{ flex: 1, width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
                    {mediaFileName ? (
                        <video
                            ref={videoRef}
                            controls
                            style={{ width: '100%', maxHeight: '100%', outline: 'none' }}
                            src={`${STATIC_BASE}/${encodeURI(mediaFileName)}`} 
                        />
                    ) : (
                        <Box sx={{ textAlign: 'center', color: '#64748b' }}>
                            <WarningAmber fontSize="large" sx={{ mb: 1, opacity: 0.5 }} />
                            <Typography>請在上方選擇正確的影片</Typography>
                        </Box>
                    )}
                </Box>
            </Box>

            {/* 右側：編輯區 */}
            <Box sx={{ width: '55%', bgcolor: '#f8fafc', overflowY: 'auto', p: 3, pb: 10 }}>
                {segments.map((seg, index) => {
                    const displaySpeaker = speakerMap[seg.speaker] || seg.speaker;
                    const isDoctor = displaySpeaker.includes('醫師') || seg.speaker === 'SPEAKER_00';
                    const absoluteDisplayTime = videoOffset + seg.start;
                    return (
                        <Box key={index} sx={{ display: 'flex', gap: 2, mb: 3 }}>
                            
                            {/* ★★★ 時間控制區 (包含新的重設按鈕) ★★★ */}
                            <Box sx={{ pt: 0.5, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 0.5 }}>
                                <Tooltip title="跳轉到此處">
                                    <Chip 
                                        label={formatTime(absoluteDisplayTime)} 
                                        onClick={() => handleJumpToTime(seg.start)} 
                                        size="small" 
                                        icon={<PlayCircleFilled sx={{ fontSize: '14px !important' }}/>} 
                                        sx={{ 
                                            cursor: 'pointer', bgcolor: '#e2e8f0', fontFamily: 'monospace', fontWeight: 'bold', 
                                            width: '85px', justifyContent: 'flex-start'
                                        }} 
                                    />
                                </Tooltip>
                                
                                <Tooltip title="將開始時間重設為目前影片進度">
                                    <IconButton 
                                        size="small" 
                                        onClick={() => handleSyncTime(index)}
                                        sx={{ color: '#94a3b8', '&:hover': { color: '#2563eb', bgcolor: '#eff6ff' } }}
                                    >
                                        <AccessTime fontSize="small" />
                                    </IconButton>
                                </Tooltip>
                            </Box>

                            <Box sx={{ flex: 1 }}>
                                <Tooltip title="點擊切換語者">
                                    <Chip label={displaySpeaker} size="small" onClick={(e) => handleSpeakerClick(e, index)} sx={{ mb: 1, fontWeight: 'bold', fontSize: '0.75rem', height: 24, bgcolor: isDoctor ? '#ecfdf5' : '#fffbeb', color: isDoctor ? '#047857' : '#b45309', border: '1px solid', borderColor: isDoctor ? '#10b981' : '#f59e0b', cursor: 'pointer' }} />
                                </Tooltip>
                                <TextField fullWidth multiline value={seg.text} onChange={(e) => handleTextChange(seg.sentence_id, e.target.value)} sx={{ bgcolor: 'white', '& .MuiOutlinedInput-root': { p: 1.5 } }} />
                                {seg.needs_review && <Alert severity="warning" icon={<WarningAmber fontSize="inherit" />} sx={{ mt: 1, py: 0, px: 1, fontSize: '0.75rem' }}>{seg.review_reason}</Alert>}
                            </Box>
                        </Box>
                    );
                })}
            </Box>
        </Box>

        {/* 選單與 Dialog */}
        <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={() => setAnchorEl(null)}>
            {allSpeakers.map(spk => <MenuItem key={spk} onClick={() => handleSelectExistingSpeaker(spk)}>{speakerMap[spk] || spk}</MenuItem>)}
            <Divider /><MenuItem onClick={handleOpenNewSpeakerDialog} sx={{color:'blue'}}><Add/> 新增...</MenuItem>
        </Menu>

        <Dialog open={isNewSpeakerDialogOpen} onClose={() => setIsNewSpeakerDialogOpen(false)}>
            <DialogTitle>新增語者</DialogTitle>
            <DialogContent><TextField autoFocus margin="dense" label="名稱" fullWidth value={newSpeakerName} onChange={(e) => setNewSpeakerName(e.target.value)} /></DialogContent>
            <DialogActions><Button onClick={() => setIsNewSpeakerDialogOpen(false)}>取消</Button><Button onClick={confirmNewSpeaker}>確認</Button></DialogActions>
        </Dialog>

        <Snackbar open={toast.open} autoHideDuration={4000} onClose={() => setToast({ ...toast, open: false })}><Alert severity={toast.type as any} variant="filled">{toast.msg}</Alert></Snackbar>
      </Box>
    </Box>
  );
}

export default App;
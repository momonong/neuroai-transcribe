import { useState, useRef, useMemo, useCallback } from 'react';
import { 
  Box, Drawer, List, ListItem, ListItemIcon, ListItemText, ListItemButton, 
  Paper, Button, Select, MenuItem, Snackbar, Alert, Typography, Divider, 
  Menu, Dialog, DialogTitle, DialogContent, TextField, DialogActions 
} from '@mui/material';
import { VideoLibrary, Save, Dashboard, Add } from '@mui/icons-material';
import axios from 'axios';

import { useTranscript } from './hooks/useTranscript';
import { TranscriptItem } from './components/TranscriptItem';

// ★ 改成相對路徑，讓 Vite Proxy 處理
const STATIC_BASE = `/static`;

function App() {
  const { 
    chunks, selectedChunk, setSelectedChunk,
    segments, speakerMap, videoOffset, mediaFileName, setMediaFileName,
    hasUnsavedChanges, loading, error,
    updateText, updateSegmentTime, updateSpeaker, renameSpeaker, save 
  } = useTranscript();

  const videoRef = useRef<HTMLVideoElement>(null);
  const [availableVideos, setAvailableVideos] = useState<{path:string, name:string}[]>([]);
  const [toast, setToast] = useState({ open: false, msg: '', type: 'info' as any });

  // Menu State
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const [activeSegmentIndex, setActiveSegmentIndex] = useState<number | null>(null);
  const [isNewSpeakerDialogOpen, setIsNewSpeakerDialogOpen] = useState(false);
  const [newSpeakerName, setNewSpeakerName] = useState("");

  // 取得影片列表 (使用相對路徑)
  useMemo(() => {
     axios.get(`/api/videos`)
       .then(res => setAvailableVideos(res.data))
       .catch(err => {
         console.error('Failed to load videos:', err);
         setToast({ open: true, msg: '無法載入影片清單', type: 'error' });
       });
  }, []);

  const allSpeakers = useMemo(() => {
    const rawSpeakers = new Set(segments.map(seg => seg.speaker));
    Object.keys(speakerMap).forEach(k => rawSpeakers.add(k));
    return Array.from(rawSpeakers).sort();
  }, [segments, speakerMap]);

  // --- Callbacks ---
  const handleJumpToTime = useCallback((relativeStart: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime = videoOffset + relativeStart;
      videoRef.current.play();
    }
  }, [videoOffset]);

  const handleSyncTime = useCallback((index: number) => {
    if (!videoRef.current) return;
    const currentAbs = videoRef.current.currentTime;
    const newRelative = Math.max(0, currentAbs - videoOffset);
    updateSegmentTime(index, newRelative);
  }, [videoOffset, updateSegmentTime]);

  const handleSaveWrapper = async () => {
      try {
          await save();
          setToast({ open: true, msg: '儲存成功', type: 'success' });
      } catch(e) {
          setToast({ open: true, msg: '儲存失敗', type: 'error' });
      }
  };

  // --- Menu Handlers ---
  const handleSpeakerClick = useCallback((event: React.MouseEvent<HTMLElement>, index: number) => {
    setAnchorEl(event.currentTarget);
    setActiveSegmentIndex(index);
  }, []);

  const handleSelectExistingSpeaker = (speakerId: string) => {
    if (activeSegmentIndex !== null) updateSpeaker(activeSegmentIndex, speakerId);
    setAnchorEl(null);
  };

  const confirmNewSpeaker = () => {
    if (activeSegmentIndex !== null && newSpeakerName.trim()) {
        updateSpeaker(activeSegmentIndex, newSpeakerName.trim());
    }
    setIsNewSpeakerDialogOpen(false);
  };

  return (
    <Box sx={{ display: 'flex', height: '100vh', bgcolor: '#0f172a', color: '#e2e8f0', fontFamily: 'Inter, sans-serif' }}>
      
      {/* 側邊欄 */}
      <Drawer variant="permanent" sx={{ width: 260, flexShrink: 0, '& .MuiPaper-root': { width: 260, bgcolor: '#1e293b', color: '#94a3b8', borderRight: '1px solid #334155' } }}>
         <Box sx={{ p: 2, display: 'flex', alignItems: 'center', gap: 1, color: '#38bdf8' }}>
            <Dashboard /><Typography variant="subtitle1" fontWeight="bold">NeuroAI Editor</Typography>
         </Box>
         
         <List sx={{ px: 1, overflowY: 'auto', flex: 1 }}>
            {chunks.length === 0 && (
                <Box sx={{ p: 2, textAlign: 'center', opacity: 0.5 }}>
                    <Typography variant="caption">沒有資料 (No Chunks)</Typography>
                </Box>
            )}
            {chunks.map(f => (
                <ListItem key={f} disablePadding sx={{ mb: 0.5 }}>
                  <ListItemButton 
                      selected={selectedChunk === f} 
                      onClick={() => setSelectedChunk(f)} 
                      sx={{ 
                          borderRadius: 1, 
                          '&.Mui-selected': { bgcolor: '#2563eb', color: 'white' },
                          '&.Mui-selected:hover': { bgcolor: '#1d4ed8' }
                      }}
                  >
                      <ListItemIcon sx={{ color: 'inherit', minWidth: 32 }}>
                          <VideoLibrary fontSize="small" />
                      </ListItemIcon>
                      <ListItemText 
                          primary={f.replace("_flagged_for_human.json", "").replace("_corrected.json", " (已修正)")} 
                          primaryTypographyProps={{ fontSize: '0.8rem', noWrap: true }} 
                      />
                  </ListItemButton>
              </ListItem>
            ))}
         </List>
      </Drawer>

      <Box component="main" sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
        
        {/* 全域錯誤提示 */}
        {error && (
          <Alert severity="error" sx={{ m: 2, mb: 0 }}>
            {error}
          </Alert>
        )}
        
        {/* TopBar */}
        <Paper square elevation={0} sx={{ height: 64, px: 3, display: 'flex', alignItems: 'center', justifyContent: 'space-between', bgcolor: '#1e293b', borderBottom: '1px solid #334155' }}>
            
            {/* Alias 編輯區 */}
            <Box sx={{ display: 'flex', gap: 2, overflowX: 'auto', alignItems: 'center', flex: 1, mr: 4 }}>
                <Typography variant="caption" sx={{ color: '#64748b', fontWeight: 'bold' }}>ALIAS:</Typography>
                {allSpeakers.map(spk => (
                    <Box key={spk} sx={{ display: 'flex', alignItems: 'center', bgcolor: '#334155', borderRadius: 8, px: 1.5, py: 0.5, border: '1px solid #475569' }}>
                        <Typography variant="caption" sx={{ color: '#94a3b8', mr: 1 }}>{spk}</Typography>
                        <input 
                            value={speakerMap[spk] || ''} 
                            onChange={(e) => renameSpeaker(spk, e.target.value)} 
                            placeholder="別名" 
                            style={{ background: 'transparent', border: 'none', color: '#fff', fontSize: '0.85rem', width: 60, outline: 'none', fontWeight: 'bold' }} 
                        />
                    </Box>
                ))}
            </Box>

            <Button 
              variant="contained" 
              color={hasUnsavedChanges ? "warning" : "primary"} 
              startIcon={<Save/>} 
              disabled={!hasUnsavedChanges || loading} 
              onClick={handleSaveWrapper}
            >
                {loading ? 'Saving...' : 'Save Changes'}
            </Button>
        </Paper>

        <Box sx={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
            
            {/* 左側：影片區 */}
            <Box sx={{ width: '45%', bgcolor: '#000', display:'flex', flexDirection:'column' }}>
                <Box sx={{ p: 1, bgcolor: '#0f172a', borderBottom: '1px solid #334155' }}>
                    <Select fullWidth size="small" value={mediaFileName} onChange={(e) => setMediaFileName(e.target.value)} sx={{color:'white', bgcolor: '#1e293b'}}>
                        {availableVideos.length === 0 && <MenuItem disabled>找不到任何影片</MenuItem>}
                        {availableVideos.map(v => <MenuItem key={v.path} value={v.path}>{v.name}</MenuItem>)}
                    </Select>
                </Box>
                <Box flex={1} display="flex" justifyContent="center" alignItems="center">
                    {mediaFileName && (
                        <video ref={videoRef} controls src={`${STATIC_BASE}/${encodeURI(mediaFileName)}`} style={{width:'100%', maxHeight:'100%'}} />
                    )}
                </Box>
            </Box>

            {/* 右側：逐字稿列表 */}
            <Box sx={{ width: '55%', bgcolor: '#f8fafc', overflowY: 'auto', p: 3, pb: 10 }}>
                {segments.length === 0 && !loading && (
                    <Box sx={{ textAlign: 'center', mt: 10, color: '#94a3b8' }}>
                        <Typography>請從左側選擇一個檔案開始編輯</Typography>
                    </Box>
                )}
                
                {segments.map((seg, index) => (
                    <TranscriptItem 
                        key={seg.sentence_id} 
                        index={index}
                        segment={seg}
                        videoOffset={videoOffset}
                        displaySpeaker={speakerMap[seg.speaker] || seg.speaker}
                        isDoctor={(speakerMap[seg.speaker] || seg.speaker).includes('醫師')}
                        
                        onTextChange={updateText}
                        onSyncTime={handleSyncTime}
                        onJumpToTime={handleJumpToTime}
                        onSpeakerClick={handleSpeakerClick}
                    />
                ))}
            </Box>
        </Box>

        {/* 選單 Components */}
        <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={() => setAnchorEl(null)}>
            {allSpeakers.map(spk => <MenuItem key={spk} onClick={() => handleSelectExistingSpeaker(spk)}>{speakerMap[spk] || spk}</MenuItem>)}
            <Divider /><MenuItem onClick={() => { setAnchorEl(null); setIsNewSpeakerDialogOpen(true); }} sx={{color:'blue'}}><Add/> 新增...</MenuItem>
        </Menu>

        <Dialog open={isNewSpeakerDialogOpen} onClose={() => setIsNewSpeakerDialogOpen(false)}>
            <DialogTitle>新增語者</DialogTitle>
            <DialogContent><TextField autoFocus margin="dense" label="名稱" fullWidth value={newSpeakerName} onChange={(e) => setNewSpeakerName(e.target.value)} /></DialogContent>
            <DialogActions><Button onClick={() => setIsNewSpeakerDialogOpen(false)}>取消</Button><Button onClick={confirmNewSpeaker}>確認</Button></DialogActions>
        </Dialog>

        <Snackbar open={toast.open} autoHideDuration={3000} onClose={() => setToast({...toast, open:false})}><Alert severity={toast.type} variant="filled">{toast.msg}</Alert></Snackbar>
      </Box>
    </Box>
  );
}

export default App;
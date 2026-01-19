import { useState, useRef, useMemo, useCallback } from 'react';
import { 
  Box, List, ListItemButton, ListItemIcon, ListItemText, 
  Paper, Button, Select, MenuItem, Snackbar, Alert, Typography, Divider, 
  Menu, Dialog, DialogTitle, DialogContent, TextField, DialogActions,
  Grid, InputAdornment, IconButton, Autocomplete
} from '@mui/material';
import { 
  VideoLibrary, Timer, FolderOpen, Add, PlayCircle, Pause
} from '@mui/icons-material';
import SkipNextIcon from '@mui/icons-material/SkipNext';
import axios from 'axios';

import { useTranscript } from './hooks/useTranscript';
import { TranscriptItem } from './components/TranscriptItem';
import { TopBar } from './components/TopBar';

const STATIC_BASE = `/static`;

function App() {
  const { 
    chunks, selectedChunk, setSelectedChunk,
    segments, speakerMap, videoOffset, mediaFileName, setMediaFileName,
    hasUnsavedChanges, loading, error,
    updateText, updateSegmentTime, updateSpeaker, renameSpeaker, save,
    deleteSegment, addSegment, uploadVideo, existingTesters, fetchTesters
  } = useTranscript();

  const videoRef = useRef<HTMLVideoElement>(null);
  const [availableVideos, setAvailableVideos] = useState<{path:string, name:string}[]>([]);
  const [toast, setToast] = useState({ open: false, msg: '', type: 'info' as any });

  // UI State
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const [activeSegmentIndex, setActiveSegmentIndex] = useState<number | null>(null);
  
  // 上傳 Dialog State
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [isNewSpeakerDialogOpen, setIsNewSpeakerDialogOpen] = useState(false);
  const [newSpeakerName, setNewSpeakerName] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [testerName, setTesterName] = useState("");
  const [isUploading, setIsUploading] = useState(false);

  // 手動跳轉時間 State
  const [jumpInput, setJumpInput] = useState("");
  const [autoPlayAfterJump, setAutoPlayAfterJump] = useState(false);

  // 取得影片列表
  useMemo(() => {
     axios.get(`/api/videos`)
       .then(res => {
         const uniqueVideos = Array.from(
             new Map(res.data.map((item: any) => [item.path, item])).values()
         ) as {path: string, name: string}[];

         setAvailableVideos(uniqueVideos);
       })
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

  // --- Functions ---

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

  const handleManualJump = () => {
    if (!videoRef.current || !jumpInput) return;
    
    let targetTime = 0;
    // 解析時間格式邏輯 (保持不變)
    if (jumpInput.includes(':')) {
        const parts = jumpInput.split(':');
        if (parts.length === 2) {
            const m = parseFloat(parts[0]);
            const s = parseFloat(parts[1]);
            targetTime = (m * 60) + s;
        } else if (parts.length === 3) {
            const h = parseFloat(parts[0]);
            const m = parseFloat(parts[1]);
            const s = parseFloat(parts[2]);
            targetTime = (h * 3600) + (m * 60) + s;
        }
    } else {
        targetTime = parseFloat(jumpInput);
    }

    if (!isNaN(targetTime)) {
        videoRef.current.currentTime = targetTime;
        
        // ★★★ 根據狀態決定行為 ★★★
        if (autoPlayAfterJump) {
            videoRef.current.play();
        } else {
            videoRef.current.pause();
        }
    }
};

  const handleSaveWrapper = async () => {
      try {
          await save();
          setToast({ open: true, msg: '儲存成功', type: 'success' });
      } catch(e) {
          setToast({ open: true, msg: '儲存失敗', type: 'error' });
      }
  };

  // ★ 這裡確保 event 被使用 (setAnchorEl)
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

  const handleUploadConfirm = async () => {
      if(!uploadFile || !testerName) return;
      setIsUploading(true);
      try {
          await uploadVideo(uploadFile, testerName);
          setToast({ open: true, msg: '上傳成功！', type: 'success' });
          setIsUploadOpen(false);
          fetchTesters();
      } catch(e) {
          setToast({ open: true, msg: '上傳失敗', type: 'error' });
      } finally {
          setIsUploading(false);
      }
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100vh', bgcolor: '#0f172a', color: '#e2e8f0' }}>
      
      {/* 1. 頂部導覽列 */}
      <TopBar 
        allSpeakers={allSpeakers}
        speakerMap={speakerMap}
        onRenameSpeaker={renameSpeaker}
        onUploadOpen={() => setIsUploadOpen(true)}
        onSave={handleSaveWrapper}
        hasUnsavedChanges={hasUnsavedChanges}
        loading={loading}
      />

      {/* 2. 主內容區 */}
      <Box sx={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          
          {/* === 左欄：影片 + 控制 + 檔案列表 === */}
          <Box sx={{ width: '40%', display: 'flex', flexDirection: 'column', borderRight: '1px solid #334155', bgcolor: '#000' }}>
              
              {/* 影片播放器 */}
              <Box sx={{ width: '100%', bgcolor: 'black', display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '200px' }}>
                  {mediaFileName ? (
                      <video 
                          ref={videoRef} 
                          controls 
                          src={`${STATIC_BASE}/${encodeURI(mediaFileName)}`} 
                          style={{ width: '100%', height: 'auto', maxHeight: '50vh', objectFit: 'contain' }} 
                      />
                  ) : (
                      <Box sx={{ p: 4, color: '#64748b', textAlign: 'center' }}>
                          <Typography>請選擇影片或 Chunk 檔案</Typography>
                      </Box>
                  )}
              </Box>

            {/* 控制面板 */}
            <Box sx={{ p: 2, bgcolor: '#0f172a', borderBottom: '1px solid #334155' }}>
                <Grid container spacing={1} alignItems="center">
                    {/* 影片選單 (佔 6 格) */}
                    <Grid size={6}>
                        <Select fullWidth size="small" value={mediaFileName} onChange={(e) => setMediaFileName(e.target.value)} sx={{ color: 'white', bgcolor: '#1e293b', '.MuiOutlinedInput-notchedOutline': { borderColor: '#475569' } }}>
                            {availableVideos.length === 0 && <MenuItem disabled>找不到任何影片</MenuItem>}
                            {availableVideos.map(v => <MenuItem key={v.path} value={v.path}>{v.name}</MenuItem>)}
                        </Select>
                    </Grid>

                    {/* 自動播放開關 (佔 1 格) */}
                    <Grid size={1} display="flex" justifyContent="center">
                        <IconButton 
                            size="small"
                            onClick={() => setAutoPlayAfterJump(!autoPlayAfterJump)}
                            title={autoPlayAfterJump ? "跳轉後自動播放" : "跳轉後暫停"}
                            sx={{ 
                                color: autoPlayAfterJump ? '#38bdf8' : '#64748b',
                                bgcolor: autoPlayAfterJump ? 'rgba(56, 189, 248, 0.1)' : 'transparent'
                            }}
                        >
                            {autoPlayAfterJump ? <PlayCircle fontSize="small" /> : <Pause fontSize="small" />}
                        </IconButton>
                    </Grid>

                    {/* 時間跳轉輸入框 (佔 5 格) */}
                    <Grid size={5}>
                        <TextField 
                            fullWidth 
                            size="small" 
                            placeholder="跳轉 (1:20)" 
                            value={jumpInput}
                            onChange={(e) => setJumpInput(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && handleManualJump()}
                            sx={{ bgcolor: '#1e293b', input: { color: 'white' }, fieldset: { borderColor: '#475569' } }}
                            InputProps={{
                                endAdornment: (
                                    <InputAdornment position="end">
                                        <IconButton size="small" onClick={handleManualJump} sx={{ color: '#38bdf8' }}>
                                            <SkipNextIcon />
                                        </IconButton>
                                    </InputAdornment>
                                ),
                                startAdornment: (
                                    <InputAdornment position="start">
                                        <Timer sx={{ color: '#64748b', fontSize: 18 }} />
                                    </InputAdornment>
                                )
                            }}
                        />
                    </Grid>
                </Grid>
            </Box>

              {/* 檔案列表 */}
              <Box sx={{ flex: 1, overflowY: 'auto', p: 2, bgcolor: '#0f172a' }}>
                  <Typography variant="subtitle2" sx={{ mb: 1, color: '#94a3b8', display: 'flex', alignItems: 'center', gap: 1 }}>
                      <FolderOpen fontSize="small"/> 專案檔案列表
                  </Typography>
                  <List disablePadding>
                      {chunks.map(f => (
                          <Paper key={f} sx={{ mb: 1, bgcolor: selectedChunk === f ? '#1e293b' : '#1e293b80', border: selectedChunk === f ? '1px solid #38bdf8' : '1px solid transparent' }}>
                              <ListItemButton 
                                  selected={selectedChunk === f} 
                                  onClick={() => setSelectedChunk(f)}
                                  sx={{ borderRadius: 1 }}
                              >
                                  <ListItemIcon sx={{ color: selectedChunk === f ? '#38bdf8' : '#64748b', minWidth: 36 }}>
                                      <VideoLibrary fontSize="small" />
                                  </ListItemIcon>
                                  <ListItemText 
                                      primary={(() => {
                                          const parts = f.split('/'); 
                                          if (parts.length >= 2) return parts[parts.length-2]; 
                                          return f.replace(".json", "");
                                      })()}
                                      secondary={f.split('/').pop()?.replace('.json', '')} 
                                      primaryTypographyProps={{ fontSize: '0.85rem', fontWeight: selectedChunk === f ? 'bold' : 'normal', color: 'white' }}
                                      secondaryTypographyProps={{ fontSize: '0.75rem', color: '#94a3b8' }}
                                  />
                              </ListItemButton>
                          </Paper>
                      ))}
                  </List>
              </Box>
          </Box>

          {/* === 右欄：逐字稿編輯區 === */}
          <Box sx={{ width: '60%', bgcolor: '#f8fafc', overflowY: 'auto', p: 3, pb: 10 }}>
              {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
              
              {segments.length === 0 && !loading && (
                  <Box sx={{ textAlign: 'center', mt: 10, color: '#94a3b8' }}>
                      <Typography>請從左下方選擇一個檔案開始編輯</Typography>
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
                      onDelete={deleteSegment}
                      onAddAfter={addSegment}
                  />
              ))}
          </Box>
      </Box>

      {/* Dialogs */}
      <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={() => setAnchorEl(null)}>
          {allSpeakers.map(spk => <MenuItem key={spk} onClick={() => handleSelectExistingSpeaker(spk)}>{speakerMap[spk] || spk}</MenuItem>)}
          <Divider /><MenuItem onClick={() => { setAnchorEl(null); setIsNewSpeakerDialogOpen(true); }} sx={{color:'blue'}}><Add/> 新增...</MenuItem>
      </Menu>

      <Dialog open={isNewSpeakerDialogOpen} onClose={() => setIsNewSpeakerDialogOpen(false)}>
          <DialogTitle>新增語者</DialogTitle>
          <DialogContent><TextField autoFocus margin="dense" label="名稱" fullWidth value={newSpeakerName} onChange={(e) => setNewSpeakerName(e.target.value)} /></DialogContent>
          <DialogActions><Button onClick={() => setIsNewSpeakerDialogOpen(false)}>取消</Button><Button onClick={confirmNewSpeaker}>確認</Button></DialogActions>
      </Dialog>

      <Dialog open={isUploadOpen} onClose={() => !isUploading && setIsUploadOpen(false)}>
          <DialogTitle>上傳新影片</DialogTitle>
          <DialogContent sx={{ pt: 2, minWidth: 400, display: 'flex', flexDirection: 'column', gap: 2 }}>
              <Autocomplete
                  freeSolo
                  options={existingTesters}
                  value={testerName}
                  onInputChange={(_event, newInputValue) => {
                      setTesterName(newInputValue);
                  }}
                  renderInput={(params) => (
                      <TextField 
                          {...params} 
                          label="測試者姓名 (Tester Name)" 
                          helperText="可選擇既有人員或輸入新名字"
                          fullWidth 
                      />
                  )}
              />
              <Button variant="outlined" component="label" fullWidth sx={{ height: 50, borderStyle: 'dashed' }}>
                  {uploadFile ? uploadFile.name : "選擇檔案 (支援 .mp4, .mp3)"}
                  <input type="file" hidden accept="video/*,audio/*" onChange={(e) => setUploadFile(e.target.files?.[0] || null)} />
              </Button>
          </DialogContent>
          <DialogActions>
              <Button onClick={() => setIsUploadOpen(false)} disabled={isUploading}>取消</Button>
              <Button onClick={handleUploadConfirm} variant="contained" disabled={isUploading || !uploadFile || !testerName}>
                  {isUploading ? "上傳中..." : "開始上傳"}
              </Button>
          </DialogActions>
      </Dialog>

      <Snackbar open={toast.open} autoHideDuration={3000} onClose={() => setToast({...toast, open:false})}><Alert severity={toast.type} variant="filled">{toast.msg}</Alert></Snackbar>
    </Box>
  );
}

export default App;
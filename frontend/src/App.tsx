import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { 
  Box, List, ListItemButton, ListItemIcon, ListItemText, 
  Paper, Button, Select, MenuItem, Snackbar, Alert, Typography, Divider, 
  Menu, Dialog, DialogTitle, DialogContent, TextField, DialogActions,
  Grid as Grid, InputAdornment, IconButton, Autocomplete, Breadcrumbs, Chip,
  LinearProgress
} from '@mui/material';
import { 
  Add, PlayCircle, Pause,
  Description, Refresh,
  Movie, Timer, FolderOpen, Edit, CheckCircle, Warning, AccessTime
} from '@mui/icons-material';
import SkipNextIcon from '@mui/icons-material/SkipNext';
import axios from 'axios';

import { useTranscript } from './hooks/useTranscript';
import { TranscriptItem } from './components/TranscriptItem';
import { TopBar } from './components/TopBar';
import { ChunkTimepoints } from './components/ChunkTimepoints';

const STATIC_BASE = `/static`;

const formatMs = (ms: number) => {
    if (isNaN(ms)) return "00:00";
    const totalSeconds = Math.floor(ms / 1000);
    const m = Math.floor(totalSeconds / 60);
    const s = totalSeconds % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
};

function App() {
  const { 
    selectedChunk, setSelectedChunk,
    segments, speakerMap, videoOffset, mediaFileName, setMediaFileName,
    chunkTimepoints, fileType,
    hasUnsavedChanges, loading, error,
    updateText, updateSegmentTime, updateSpeaker, renameSpeaker, save,
    deleteSegment, addSegment, uploadVideo, existingTesters, fetchTesters,
    resolveFlag 
  } = useTranscript();

  const videoRef = useRef<HTMLVideoElement>(null);
  const [availableVideos, setAvailableVideos] = useState<{path:string, name:string}[]>([]);
  const [toast, setToast] = useState({ open: false, msg: '', type: 'info' as any });

  const [selectedCase, setSelectedCase] = useState<string | null>(null);
  const [caseChunks, setCaseChunks] = useState<string[]>([]); 
  
  // UI State
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const [activeSegmentIndex, setActiveSegmentIndex] = useState<number | null>(null);
  
  // Dialogs & Upload
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [isNewSpeakerDialogOpen, setIsNewSpeakerDialogOpen] = useState(false);
  const [newSpeakerName, setNewSpeakerName] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadCaseName, setUploadCaseName] = useState("");
  
  // ★ 修改：進度條相關 State
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState(""); // 顯示後端回傳的 step + message

  // Playback
  const [jumpInput, setJumpInput] = useState("");
  const [autoPlayAfterJump, setAutoPlayAfterJump] = useState(false);

  const fetchVideos = () => {
     axios.get(`/api/videos`)
       .then(res => {
         const uniqueVideos = Array.from(
             new Map(res.data.map((item: any) => [item.path, item])).values()
         ) as {path: string, name: string}[];
         setAvailableVideos(uniqueVideos);
       })
       .catch(console.error);
  };

  useEffect(() => {
      fetchVideos();
  }, []);

  useEffect(() => {
      if (mediaFileName) {
          const parts = mediaFileName.split('/');
          if (parts.length >= 2) {
              const caseName = parts[0];
              setSelectedCase(caseName);
              axios.get(`/api/temp/chunks?case=${caseName}`)
                   .then(res => {
                       setCaseChunks(res.data.files);
                   })
                   .catch(console.error);
          }
      }
  }, [mediaFileName]);

  // --- Handlers ---
  const handleJumpToTime = useCallback((relativeStart: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime = relativeStart;
      videoRef.current.play();
    }
  }, []);

  const handleSyncTime = useCallback((index: number) => {
    if (!videoRef.current) return;
    const currentAbs = videoRef.current.currentTime;
    const newRelative = Math.max(0, currentAbs - videoOffset);
    updateSegmentTime(index, newRelative);
  }, [videoOffset, updateSegmentTime]);

  const handleManualJump = () => {
    if (!videoRef.current || !jumpInput) return;
    let targetTime = 0;
    if (jumpInput.includes(':')) {
        const parts = jumpInput.split(':');
        if (parts.length === 2) {
            targetTime = (parseFloat(parts[0]) * 60) + parseFloat(parts[1]);
        }
    } else {
        targetTime = parseFloat(jumpInput);
    }
    if (!isNaN(targetTime)) {
        videoRef.current.currentTime = targetTime;
        autoPlayAfterJump ? videoRef.current.play() : videoRef.current.pause();
    }
  };

  const handleSaveWrapper = async () => {
      try {
          await save();
          setToast({ open: true, msg: '儲存成功！', type: 'success' });

          if (selectedCase && selectedChunk) {
              const res = await axios.get(`/api/temp/chunks?case=${selectedCase}`);
              const newFiles = res.data.files;
              setCaseChunks(newFiles);

              const currentChunkId = selectedChunk.split('/').pop()?.split('_').slice(0, 2).join('_');
              const newMatchingFile = newFiles.find((f: string) => f.includes(currentChunkId || ""));
              
              if (newMatchingFile && newMatchingFile !== selectedChunk) {
                  console.log("🔄 Auto-switching to edited file:", newMatchingFile);
                  setSelectedChunk(newMatchingFile);
              }
          }
      } catch(e) {
          console.error(e);
          setToast({ open: true, msg: '儲存失敗', type: 'error' });
      }
  };

  const handleSpeakerClick = useCallback((event: React.MouseEvent<HTMLElement>, index: number) => {
    setAnchorEl(event.currentTarget);
    setActiveSegmentIndex(index);
  }, []);

  const handleSelectExistingSpeaker = (speakerId: string) => {
    if (activeSegmentIndex !== null) updateSpeaker(activeSegmentIndex, speakerId);
    setAnchorEl(null);
  };

  // ★★★ 核心修改：輪詢 (Polling) 邏輯 ★★★
  const handleUploadConfirm = async () => {
      if(!uploadFile || !uploadCaseName) return;
      
      setIsUploading(true);
      setUploadProgress(0);
      setCurrentStep("Initiating Upload...");

      try {
          // 1. 發送上傳請求 (現在後端會秒回 "processing_started")
          await uploadVideo(uploadFile, uploadCaseName);
          
          setCurrentStep("Upload Complete. Starting AI Pipeline...");

          // 2. 開始輪詢狀態
          const pollInterval = setInterval(async () => {
              try {
                  // 呼叫我們剛寫好的 get_status API
                  const res = await axios.get(`/api/status/${uploadCaseName}`);
                  const { progress, step, message } = res.data;

                  // 更新 UI
                  setUploadProgress(progress);
                  setCurrentStep(`${step}: ${message}`);

                  // 3. 判斷是否結束
                  if (progress >= 100) {
                      clearInterval(pollInterval);
                      setToast({ open: true, msg: 'Pipeline 執行成功！', type: 'success' });
                      
                      setTimeout(() => {
                          setIsUploadOpen(false);
                          setUploadProgress(0);
                          setIsUploading(false);
                          fetchVideos();
                          fetchTesters();
                      }, 1000);
                  } 
                  else if (step === "Error" || progress === -1) {
                      clearInterval(pollInterval);
                      setIsUploading(false);
                      setToast({ open: true, msg: `處理失敗: ${message}`, type: 'error' });
                  }
              } catch (err) {
                  // 網路錯誤等，不中斷，繼續試
                  console.warn("Polling error:", err);
              }
          }, 2000); // 每 2 秒問一次

      } catch(e) {
          setIsUploading(false);
          setToast({ open: true, msg: '上傳失敗，請檢查後端日誌', type: 'error' });
      }
  };

  const allSpeakers = useMemo(() => {
    const s = new Set<string>();
    segments.forEach(seg => s.add(seg.speaker));
    Object.keys(speakerMap).forEach(k => s.add(k));
    return Array.from(s).sort();
  }, [segments, speakerMap]);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100vh', width: '100vw', bgcolor: '#0f172a', color: '#e2e8f0', overflow: 'hidden' }}>
      
      <TopBar 
        allSpeakers={allSpeakers}
        speakerMap={speakerMap}
        onRenameSpeaker={renameSpeaker}
        onUploadOpen={() => setIsUploadOpen(true)}
        onSave={handleSaveWrapper}
        hasUnsavedChanges={hasUnsavedChanges}
        loading={loading}
      />

      <Box sx={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          
          {/* === 左欄：側邊欄 (固定 40%) === */}
          <Box sx={{ width: '40%', minWidth: '400px', display: 'flex', flexDirection: 'column', borderRight: '1px solid #334155', bgcolor: '#0f172a' }}>
              
              {/* A. 影片播放器 */}
              <Box sx={{ 
                  width: '100%', 
                  bgcolor: '#000', 
                  display: 'flex', 
                  justifyContent: 'center', 
                  alignItems: 'center', 
                  minHeight: '300px', 
                  flexShrink: 0,
                  borderBottom: '1px solid #334155',
                  position: 'relative'
              }}>
                  {mediaFileName ? (
                      <video 
                          ref={videoRef} 
                          controls 
                          src={`${STATIC_BASE}/${encodeURI(mediaFileName)}`} 
                          style={{ width: '100%', height: '100%', maxHeight: '45vh', objectFit: 'contain' }} 
                      />
                  ) : (
                      <Box sx={{ p: 4, color: '#64748b', textAlign: 'center', display:'flex', flexDirection:'column', alignItems:'center', gap:1 }}>
                          <Movie sx={{ fontSize: 48, opacity: 0.5 }}/>
                          <Typography variant="body2">請從下方選擇影片</Typography>
                      </Box>
                  )}
              </Box>

              {/* B. 播放控制區 */}
              <Box sx={{ p: 2, bgcolor: '#1e293b', borderBottom: '1px solid #334155' }}>
                  <Grid container spacing={1} alignItems="center">
                    <Grid size={12}>
                        <Select 
                            fullWidth size="small" 
                            value={mediaFileName || ""} 
                            onChange={(e) => setMediaFileName(e.target.value)} 
                            displayEmpty
                            sx={{ color: 'white', bgcolor: '#0f172a', '.MuiOutlinedInput-notchedOutline': { borderColor: '#475569' } }}
                        >
                            <MenuItem value="" disabled>-- 切換案例 (影片) --</MenuItem>
                            {availableVideos.map(v => (
                                <MenuItem key={v.path} value={v.path}>{v.name}</MenuItem>
                            ))}
                        </Select>
                    </Grid>
                    <Grid size={12} display="flex" gap={1} mt={1}>
                        <TextField 
                            fullWidth size="small" placeholder="跳轉 (例如 1:20)" value={jumpInput} onChange={e=>setJumpInput(e.target.value)} onKeyDown={e=>e.key==='Enter'&&handleManualJump()}
                            sx={{ bgcolor: '#0f172a', input:{color:'white'}, fieldset:{borderColor:'#475569'} }}
                            InputProps={{
                                startAdornment: <InputAdornment position="start"><Timer sx={{color:'#64748b', fontSize:18}}/></InputAdornment>,
                                endAdornment: <IconButton size="small" onClick={handleManualJump}><SkipNextIcon sx={{color:'#38bdf8'}}/></IconButton>
                            }}
                        />
                        <IconButton onClick={()=>setAutoPlayAfterJump(!autoPlayAfterJump)} sx={{color: autoPlayAfterJump?'#38bdf8':'#64748b', border:'1px solid #334155'}}>
                            {autoPlayAfterJump ? <PlayCircle/> : <Pause/>}
                        </IconButton>
                    </Grid>
                  </Grid>
              </Box>

              {/* C. 檔案列表區 */}
              <Box sx={{ flex: 1, overflowY: 'auto', p: 2, bgcolor: '#0f172a' }}>
                  
                  <Box sx={{ mb: 1.5, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <Typography variant="subtitle2" sx={{ color: '#94a3b8', display: 'flex', alignItems: 'center', gap: 1 }}>
                          <FolderOpen fontSize="small"/> 
                          {selectedCase ? '段落列表 (Chunks)' : '請先選擇影片'}
                      </Typography>
                      <IconButton size="small" onClick={() => { if(selectedCase) axios.get(`/api/temp/chunks?case=${selectedCase}`).then(res => setCaseChunks(res.data.files)); }}><Refresh fontSize="small" sx={{color:'#64748b'}}/></IconButton>
                  </Box>

                  <List disablePadding>
                      {selectedCase && caseChunks.length === 0 && (
                          <Box sx={{textAlign:'center', mt:4, color:'#64748b'}}>
                              <Typography variant="body2">此影片沒有可用的段落檔案</Typography>
                          </Box>
                      )}

                      {caseChunks.map(f => {
                          const fileName = f.split('/').pop() || "";
                          const parts = fileName.split('_');
                          
                          let displayName = fileName;
                          let timeRange = "";
                          let chunkIndex = "";

                          if (parts.length >= 4) {
                              const idx = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"];
                              const num = parseInt(parts[1]);
                              const numStr = num <= 10 ? idx[num] : num;
                              
                              chunkIndex = `第 ${numStr} 段`;
                              
                              const start = formatMs(parseInt(parts[2]));
                              const end = formatMs(parseInt(parts[3]));
                              timeRange = `${start} - ${end}`;
                              
                              displayName = chunkIndex;
                          }

                          const isSelected = selectedChunk === f;
                          const isFlagged = f.includes('flagged');
                          const isEdited = f.includes('edited');
                          const isOriginal = !isFlagged && !isEdited;
                          
                          return (
                              <Paper 
                                  key={f} 
                                  elevation={0}
                                  sx={{ 
                                      mb: 1, 
                                      bgcolor: isSelected ? '#334155' : '#1e293b', 
                                      border: '1px solid',
                                      borderColor: isSelected ? '#38bdf8' : '#334155',
                                      transition: 'all 0.1s',
                                      cursor: 'pointer',
                                      '&:hover': { borderColor: '#64748b' }
                                  }}
                              >
                                  <ListItemButton onClick={() => setSelectedChunk(f)} selected={isSelected} sx={{py: 1.5}}>
                                      <ListItemIcon sx={{ color: isSelected ? '#38bdf8' : '#94a3b8', minWidth: 40 }}>
                                          <Description fontSize="medium" />
                                      </ListItemIcon>
                                      
                                      <ListItemText 
                                          disableTypography
                                          primary={
                                              <Box display="flex" alignItems="center" justifyContent="space-between">
                                                  <Typography fontWeight={600} color={isSelected?'white':'#e2e8f0'}>
                                                      {displayName}
                                                  </Typography>
                                                  
                                                  {isFlagged && <Chip label="需人工審核" size="small" color="warning" sx={{height:20, fontSize:'0.7rem'}} icon={<Warning style={{fontSize:12}}/>} />}
                                                  {isEdited && <Chip label="已編輯" size="small" color="success" sx={{height:20, fontSize:'0.7rem'}} icon={<CheckCircle style={{fontSize:12}}/>} />}
                                                  {isOriginal && <Chip label="原始檔" size="small" sx={{height:20, fontSize:'0.7rem', bgcolor:'transparent', border:'1px solid #64748b', color:'#94a3b8'}} />}
                                              </Box>
                                          } 
                                          secondary={
                                              <Box display="flex" alignItems="center" gap={0.5} mt={0.5} color="#94a3b8">
                                                  <AccessTime sx={{fontSize:14}}/>
                                                  <Typography variant="caption" sx={{fontFamily: 'monospace'}}>
                                                      {timeRange}
                                                  </Typography>
                                              </Box>
                                          }
                                      />
                                  </ListItemButton>
                              </Paper>
                          );
                      })}
                  </List>
              </Box>
          </Box>

          {/* === 右欄：編輯區 (固定 60%) === */}
          <Box sx={{ width: '60%', bgcolor: '#f8fafc', overflowY: 'auto', p: 4, pb: 10 }}>
              {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

              {selectedChunk ? (
                  <Box sx={{ mb: 4, pb: 2, borderBottom: '1px solid #e2e8f0' }}>
                      <Breadcrumbs aria-label="breadcrumb" sx={{mb: 1, fontSize: '0.85rem'}}>
                           <Typography color="text.secondary">{selectedCase}</Typography>
                           <Typography color="text.primary">編輯中</Typography>
                      </Breadcrumbs>
                      
                      <Typography variant="h5" color="#1e293b" fontWeight={600} display="flex" alignItems="center" gap={1}>
                          <Edit fontSize="medium" color="primary"/>
                          {(() => {
                              const parts = selectedChunk.split('/').pop()?.split('_') || [];
                              const idx = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"];
                              const num = parseInt(parts[1]);
                              const numStr = num <= 10 ? idx[num] : num;
                              if (parts.length >= 2) return `編輯：第 ${numStr} 段`;
                              return "編輯內容";
                          })()}
                      </Typography>
                      
                      <Box sx={{mt: 2}}>
                        <ChunkTimepoints chunkTimepoints={chunkTimepoints} onJumpToTime={handleJumpToTime} fileType={fileType} />
                      </Box>
                  </Box>
              ) : (
                  <Box sx={{ textAlign: 'center', mt: 15, color: '#94a3b8' }}>
                      <Description sx={{ fontSize: 80, opacity: 0.1, mb: 2 }} />
                      <Typography variant="h6">請選擇段落</Typography>
                      <Typography variant="body2">請點擊左側列表中的段落以開始編輯。</Typography>
                  </Box>
              )}

              <Box sx={{ maxWidth: '900px', mx: 'auto' }}>
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
                        onResolveFlag={resolveFlag} 
                    />
                ))}
              </Box>
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
          <DialogActions><Button onClick={() => setIsNewSpeakerDialogOpen(false)}>取消</Button><Button onClick={() => {if(activeSegmentIndex!==null && newSpeakerName) updateSpeaker(activeSegmentIndex, newSpeakerName); setIsNewSpeakerDialogOpen(false);}}>確認</Button></DialogActions>
      </Dialog>

      {/* ★ 上傳與進度 Dialog ★ */}
      <Dialog 
          open={isUploadOpen} 
          onClose={() => !isUploading && setIsUploadOpen(false)}
          maxWidth="sm"
          fullWidth
      >
          <DialogTitle sx={{ pb: 1 }}>
              上傳新案例與執行 Pipeline
          </DialogTitle>
          
          <DialogContent sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 3 }}>
              {/* 修復標題被切掉：增加 mt: 1 */}
              <Autocomplete
                  freeSolo
                  options={existingTesters || []}
                  value={uploadCaseName}
                  onInputChange={(_, v) => setUploadCaseName(v)}
                  renderInput={(params) => (
                      <TextField 
                          {...params} 
                          label="案例名稱 (Case Name)" 
                          fullWidth 
                          variant="outlined"
                          sx={{ mt: 1 }} 
                      />
                  )}
              />

              {!isUploading ? (
                  // === 狀態 A: 等待上傳 (大按鈕) ===
                  <Button 
                      variant="outlined" 
                      component="label" 
                      fullWidth 
                      sx={{ 
                          height: 120, 
                          borderStyle: 'dashed', 
                          borderWidth: 2,
                          borderColor: uploadFile ? '#38bdf8' : '#94a3b8',
                          bgcolor: uploadFile ? 'rgba(56, 189, 248, 0.05)' : 'transparent',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: 1,
                          '&:hover': {
                              borderWidth: 2,
                              borderColor: '#38bdf8',
                              bgcolor: 'rgba(56, 189, 248, 0.1)'
                          }
                      }}
                  >
                      {uploadFile ? (
                          <>
                              <Movie fontSize="large" color="primary"/>
                              <Typography variant="h6" color="primary">{uploadFile.name}</Typography>
                              <Typography variant="caption" color="text.secondary">點擊更換檔案</Typography>
                          </>
                      ) : (
                          <>
                              <Add fontSize="large" sx={{ opacity: 0.5 }}/>
                              <Typography variant="h6" color="text.secondary">選擇影片檔案</Typography>
                              <Typography variant="caption" color="text.secondary">支援 .mp4, .wav</Typography>
                          </>
                      )}
                        <input 
                            type="file" 
                            hidden 
                            accept="video/*,audio/*" 
                            onChange={(e) => {
                                const file = e.target.files?.[0] || null;
                                setUploadFile(file);
                                
                                // ★ 新增：自動將檔名填入案例名稱 (移除副檔名)
                                if (file) {
                                    const fileNameWithoutExt = file.name.replace(/\.[^/.]+$/, "");
                                    setUploadCaseName(fileNameWithoutExt);
                                }
                            }} 
                        />
                  </Button>
              ) : (
                  // === 狀態 B: 真實進度條 (Polling) ===
                  <Paper variant="outlined" sx={{ p: 3, bgcolor: '#f8fafc', borderColor: '#cbd5e1' }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', mb: 1, justifyContent: 'space-between' }}>
                          <Typography variant="subtitle1" fontWeight="bold" color="#0f172a">
                              {currentStep}
                          </Typography>
                          <Typography variant="h6" color="primary" fontWeight="bold">
                              {Math.round(uploadProgress)}%
                          </Typography>
                      </Box>
                      
                      <Box sx={{ width: '100%', mr: 1 }}>
                          <LinearProgress 
                              variant="determinate" 
                              value={uploadProgress} 
                              sx={{ 
                                  height: 10, 
                                  borderRadius: 5,
                                  bgcolor: '#e2e8f0',
                                  '& .MuiLinearProgress-bar': {
                                      borderRadius: 5,
                                      bgcolor: '#3b82f6' 
                                  }
                              }}
                          />
                      </Box>
                      
                      <Typography variant="caption" sx={{ display:'block', mt: 1.5, color: '#64748b' }}>
                          正在後端進行 AI 運算 (可關閉視窗，後台將繼續執行)
                      </Typography>
                  </Paper>
              )}

          </DialogContent>
          
          <DialogActions sx={{ px: 3, pb: 3 }}>
              <Button onClick={() => setIsUploadOpen(false)} disabled={isUploading} size="large">
                  取消
              </Button>
              
              {!isUploading && (
                  <Button 
                      onClick={handleUploadConfirm} 
                      variant="contained" 
                      size="large"
                      disabled={!uploadFile || !uploadCaseName}
                      startIcon={<PlayCircle />}
                      sx={{ px: 4 }}
                  >
                      開始執行 Pipeline
                  </Button>
              )}
          </DialogActions>
      </Dialog>

      <Snackbar open={toast.open} autoHideDuration={3000} onClose={() => setToast({...toast, open:false})}><Alert severity={toast.type} variant="filled">{toast.msg}</Alert></Snackbar>
    </Box>
  );
}

export default App;
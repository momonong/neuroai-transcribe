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
  Movie, Timer, FolderOpen, Edit, CheckCircle, Warning, AccessTime,
  Download, AutoFixHigh, GraphicEq, RecordVoiceOver, Cable // ★ 新增圖示
} from '@mui/icons-material';
import SkipNextIcon from '@mui/icons-material/SkipNext';
import axios from 'axios';

import { setAuthToken, TOKEN_KEY, updateCaseTask, type CaseTaskPatchResponse } from './apiClient';
import { useTranscript } from './hooks/useTranscript';
import { TranscriptItem } from './components/TranscriptItem';
import { TopBar } from './components/TopBar';
import { ChunkTimepoints } from './components/ChunkTimepoints';

const STATIC_BASE = `/static`;

type ProjectMember = { user_id: number; real_name: string };
type ProjectRow = { id: number; name: string; members: ProjectMember[] };
type VideoRow = {
  path: string;
  name: string;
  case_name: string;
  status: string;
  assignee_id: number | null;
  assignee_real_name: string | null;
};

/** 依 case_name 保留第一筆，避免下拉出現重複條目（與後端單案單檔回傳互為防呆） */
function dedupeVideoRowsByCase(rows: VideoRow[]): VideoRow[] {
  const seen = new Map<string, VideoRow>();
  for (const r of rows) {
    if (!seen.has(r.case_name)) seen.set(r.case_name, r);
  }
  return Array.from(seen.values()).sort((a, b) =>
    a.name < b.name ? 1 : a.name > b.name ? -1 : 0,
  );
}

const DEFAULT_PROJECT_NAME = '預設專案 (Default Project)';

/** 登入／註冊表單：白底；抵消 Chrome 對密碼欄 autofill 的灰色底。 */
const AUTH_DIALOG_TEXT_FIELD_SX = {
  '& .MuiOutlinedInput-root': { backgroundColor: '#fff' },
  '& input:-webkit-autofill': {
    WebkitBoxShadow: '0 0 0 1000px #fff inset',
    WebkitTextFillColor: 'rgba(0, 0, 0, 0.87)',
  },
} as const;

const STATUS_LABELS: Record<string, string> = {
  PENDING: '未開始',
  IN_PROGRESS: '進行中',
  COMPLETED: '已完成',
};

const formatMs = (ms: number) => {
    if (isNaN(ms)) return "00:00";
    const totalSeconds = Math.floor(ms / 1000);
    const m = Math.floor(totalSeconds / 60);
    const s = totalSeconds % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
};

function App() {
  const [loggedIn, setLoggedIn] = useState(() => !!localStorage.getItem(TOKEN_KEY));
  const [projects, setProjects] = useState<ProjectRow[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [videoRows, setVideoRows] = useState<VideoRow[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [assigneeFilter, setAssigneeFilter] = useState<string>('');
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');
  const [authUser, setAuthUser] = useState('');
  const [authPass, setAuthPass] = useState('');
  const [authRealName, setAuthRealName] = useState('');

  const {
    selectedChunk,
    setSelectedChunk,
    segments,
    speakerMap,
    videoOffset,
    mediaFileName,
    setMediaFileName,
    chunkTimepoints,
    fileType,
    hasUnsavedChanges,
    loading,
    error,
    updateText,
    updateSegmentTime,
    updateSegmentEndTime,
    updateSpeaker,
    renameSpeaker,
    save,
    deleteSegment,
    addSegment,
    uploadVideo,
    existingTesters,
    fetchTesters,
    resolveFlag,
  } = useTranscript(selectedProjectId);

  const videoRef = useRef<HTMLVideoElement>(null);
  const [toast, setToast] = useState({ open: false, msg: '', type: 'info' as 'success' | 'error' | 'info' | 'warning' });

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
  
  // ★ 下載選單 State
  const [downloadAnchor, setDownloadAnchor] = useState<null | HTMLElement>(null);

  // ★ 進度條相關 State
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState(""); 

  // Playback
  const [jumpInput, setJumpInput] = useState("");
  const [autoPlayAfterJump, setAutoPlayAfterJump] = useState(false);

  const loadVideoRows = useCallback(() => {
    if (selectedProjectId == null) {
      setVideoRows([]);
      return;
    }
    axios
      .get<VideoRow[]>('/api/videos', { params: { project_id: selectedProjectId } })
      .then((res) => {
        const rows = dedupeVideoRowsByCase(res.data);
        setVideoRows(rows);
        setMediaFileName((prev) => {
          if (prev && rows.some((v) => v.path === prev)) return prev;
          const demo = rows.find((v) => v.case_name === 'default_demo');
          const pick = demo ?? rows[0];
          return pick ? pick.path : '';
        });
      })
      .catch(() => setVideoRows([]));
  }, [selectedProjectId, setMediaFileName]);

  useEffect(() => {
    if (!loggedIn) {
      setProjects([]);
      setSelectedProjectId(null);
      return;
    }
    axios
      .get<ProjectRow[]>('/api/projects/my')
      .then((res) => {
        setProjects(res.data);
        setSelectedProjectId((prev) => {
          if (prev != null && res.data.some((p) => p.id === prev)) return prev;
          if (!res.data.length) return null;
          const preferred = res.data.find((p) => p.name === DEFAULT_PROJECT_NAME);
          return preferred?.id ?? res.data[0].id;
        });
      })
      .catch(() => setProjects([]));
  }, [loggedIn]);

  useEffect(() => {
    loadVideoRows();
  }, [loadVideoRows]);

  const currentProject = useMemo(
    () => projects.find((p) => p.id === selectedProjectId) ?? null,
    [projects, selectedProjectId],
  );

  const assigneeOptions = useMemo(() => {
    const names = new Set<string>();
    videoRows.forEach((v) => {
      if (v.assignee_real_name) names.add(v.assignee_real_name);
    });
    currentProject?.members.forEach((m) => names.add(m.real_name));
    return Array.from(names).sort();
  }, [videoRows, currentProject]);

  const filteredVideos = useMemo(() => {
    const filtered = videoRows.filter((v) => {
      if (statusFilter && v.status !== statusFilter) return false;
      if (assigneeFilter === '__unassigned__') return !v.assignee_real_name;
      if (assigneeFilter) return v.assignee_real_name === assigneeFilter;
      return true;
    });
    const byCase = new Map<string, VideoRow>();
    for (const v of filtered) {
      if (!byCase.has(v.case_name)) byCase.set(v.case_name, v);
    }
    return Array.from(byCase.values()).sort((a, b) =>
      a.name < b.name ? 1 : a.name > b.name ? -1 : 0,
    );
  }, [videoRows, statusFilter, assigneeFilter]);

  const currentVideoRow = useMemo(() => {
    if (!mediaFileName) return null;
    const byPath = videoRows.find((v) => v.path === mediaFileName);
    if (byPath) return byPath;
    const caseName = mediaFileName.split('/')[0] ?? '';
    return videoRows.find((v) => v.case_name === caseName) ?? null;
  }, [mediaFileName, videoRows]);

  const mergeCaseIntoVideoRows = useCallback((data: CaseTaskPatchResponse) => {
    setVideoRows((prev) =>
      prev.map((r) =>
        r.case_name === data.case_name
          ? {
              ...r,
              status: data.status,
              assignee_id: data.assignee_id,
              assignee_real_name: data.assignee_real_name,
            }
          : r,
      ),
    );
  }, []);

  const handleCurrentCaseStatusChange = async (newStatus: string) => {
    const cn = currentVideoRow?.case_name;
    if (!cn) return;
    try {
      const res = await updateCaseTask(cn, { status: newStatus });
      mergeCaseIntoVideoRows(res);
      setToast({ open: true, msg: '狀態已更新', type: 'success' });
    } catch {
      setToast({ open: true, msg: '更新狀態失敗', type: 'error' });
    }
  };

  const handleCurrentCaseAssigneeChange = async (raw: string) => {
    const cn = currentVideoRow?.case_name;
    if (!cn) return;
    const assignee_id = raw === '__unassigned__' ? null : Number(raw);
    try {
      const res = await updateCaseTask(cn, { assignee_id });
      mergeCaseIntoVideoRows(res);
      setToast({ open: true, msg: '負責人已更新', type: 'success' });
    } catch {
      setToast({ open: true, msg: '更新負責人失敗', type: 'error' });
    }
  };

  useEffect(() => {
    if (!mediaFileName) return;
    if (!filteredVideos.some((v) => v.path === mediaFileName)) {
      setMediaFileName('');
    }
  }, [filteredVideos, mediaFileName, setMediaFileName]);

  const handleLogin = async () => {
    try {
      const res = await axios.post<{ access_token: string }>('/api/auth/login', {
        username: authUser,
        password: authPass,
      });
      setAuthToken(res.data.access_token);
      setLoggedIn(true);
      setToast({ open: true, msg: '登入成功', type: 'success' });
    } catch {
      setToast({ open: true, msg: '登入失敗', type: 'error' });
    }
  };

  const handleRegister = async () => {
    const rn = authRealName.trim();
    if (!rn) {
      setToast({ open: true, msg: '請填寫顯示名稱（real_name）', type: 'warning' });
      return;
    }
    try {
      await axios.post('/api/auth/register', {
        username: authUser,
        password: authPass,
        real_name: rn,
      });
      setToast({ open: true, msg: '註冊成功，請登入', type: 'success' });
      setAuthMode('login');
    } catch (e: unknown) {
      const ax = e as { response?: { data?: { detail?: unknown } } };
      const d = ax.response?.data?.detail;
      const msg = typeof d === 'string' ? d : '註冊失敗';
      setToast({ open: true, msg, type: 'error' });
    }
  };

  const handleLogout = () => {
    setAuthToken(null);
    setLoggedIn(false);
    setProjects([]);
    setSelectedProjectId(null);
    setVideoRows([]);
    setMediaFileName('');
  };

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

  const handleSyncEndTime = useCallback((index: number) => {
    if (!videoRef.current) return;
    const currentAbs = videoRef.current.currentTime;
    const newRelative = Math.max(0, currentAbs - videoOffset);
    updateSegmentEndTime(index, newRelative);
  }, [videoOffset, updateSegmentEndTime]);

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
          setToast({ open: true, msg: 'Saved successfully!', type: 'success' });

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
          setToast({ open: true, msg: 'Save failed', type: 'error' });
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

  // ★ 新增：下載處理函式 (解決 window.open 被擋的問題)
  const handleDownloadFile = (type: string) => {
      if (!selectedCase) return;
      
      // 建立隱藏的 a 標籤來觸發下載
      const link = document.createElement('a');
      link.href = `/api/export/${selectedCase}/${type}`;
      link.setAttribute('download', `${selectedCase}_${type}.json`); // 建議檔名
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      setDownloadAnchor(null); // 關閉選單
  };

  // ★ 上傳 Polling 邏輯
  const handleUploadConfirm = async () => {
      if (!uploadFile || !uploadCaseName || selectedProjectId == null) return;
      
      setIsUploading(true);
      setUploadProgress(0);
      setCurrentStep("Initiating Upload...");

      try {
          await uploadVideo(uploadFile, uploadCaseName, selectedProjectId);
          
          setCurrentStep("Upload Complete. Starting AI Pipeline...");

          const pollInterval = setInterval(async () => {
              try {
                  const res = await axios.get(`/api/status/${uploadCaseName}`);
                  const { progress, step, message } = res.data;

                  setUploadProgress(progress);
                  setCurrentStep(`${step}: ${message}`);

                  if (progress >= 100) {
                      clearInterval(pollInterval);
                      setToast({ open: true, msg: 'Pipeline completed successfully!', type: 'success' });
                      
                      setTimeout(() => {
                          setIsUploadOpen(false);
                          setUploadProgress(0);
                          setIsUploading(false);
                          loadVideoRows();
                          fetchTesters();
                      }, 1000);
                  } 
                  else if (step === "Error" || progress === -1) {
                      clearInterval(pollInterval);
                      setIsUploading(false);
                      setToast({ open: true, msg: `Processing failed: ${message}`, type: 'error' });
                  }
              } catch (err) {
                  console.warn("Polling error:", err);
              }
          }, 2000); 

      } catch(e) {
          setIsUploading(false);
          setToast({ open: true, msg: 'Upload failed. Please check backend logs.', type: 'error' });
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
        onLogout={loggedIn ? handleLogout : undefined}
      />

      <Box sx={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          
          {/* === 左欄：側邊欄 (固定 40%) — 播放器佔較大垂直空間，Chunks 區縮小可捲動 === */}
          <Box sx={{ width: '40%', minWidth: '400px', height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column', borderRight: '1px solid #334155', bgcolor: '#0f172a', overflow: 'hidden' }}>

              {currentVideoRow && (
                <Box
                  sx={{
                    px: 2,
                    py: 1.5,
                    bgcolor: '#1e293b',
                    borderBottom: '1px solid #334155',
                    flexShrink: 0,
                  }}
                >
                  <Typography variant="subtitle2" sx={{ color: '#94a3b8', mb: 1, display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    <Movie sx={{ fontSize: 18, opacity: 0.9 }} />
                    當前影片設定
                  </Typography>
                  <Grid container spacing={1}>
                    <Grid size={6}>
                      <Select
                        fullWidth
                        size="small"
                        value={currentVideoRow.status}
                        onChange={(e) => handleCurrentCaseStatusChange(String(e.target.value))}
                        sx={{
                          color: 'white',
                          bgcolor: '#0f172a',
                          '.MuiOutlinedInput-notchedOutline': { borderColor: '#475569' },
                        }}
                      >
                        {Object.entries(STATUS_LABELS).map(([k, label]) => (
                          <MenuItem key={k} value={k}>
                            {label}
                          </MenuItem>
                        ))}
                      </Select>
                    </Grid>
                    <Grid size={6}>
                      <Select
                        fullWidth
                        size="small"
                        value={
                          currentVideoRow.assignee_id == null
                            ? '__unassigned__'
                            : String(currentVideoRow.assignee_id)
                        }
                        onChange={(e) => handleCurrentCaseAssigneeChange(String(e.target.value))}
                        sx={{
                          color: 'white',
                          bgcolor: '#0f172a',
                          '.MuiOutlinedInput-notchedOutline': { borderColor: '#475569' },
                        }}
                      >
                        <MenuItem value="__unassigned__">未指派</MenuItem>
                        {(currentProject?.members ?? []).map((m) => (
                          <MenuItem key={m.user_id} value={String(m.user_id)}>
                            {m.real_name}
                          </MenuItem>
                        ))}
                      </Select>
                    </Grid>
                  </Grid>
                </Box>
              )}
              
              {/* A. 影片播放器 */}
              <Box sx={{ 
                  width: '100%', 
                  bgcolor: '#000', 
                  display: 'flex', 
                  justifyContent: 'center', 
                  alignItems: 'center', 
                  flex: '2 1 0%',
                  minHeight: 280,
                  borderBottom: '1px solid #334155',
                  position: 'relative'
              }}>
                  {mediaFileName ? (
                      <video 
                          ref={videoRef} 
                          controls 
                          src={`${STATIC_BASE}/${encodeURI(mediaFileName)}`} 
                          style={{ width: '100%', height: '100%', maxHeight: 'min(62vh, 100%)', minHeight: 240, objectFit: 'contain' }} 
                      />
                  ) : (
                      <Box sx={{ p: 4, color: '#64748b', textAlign: 'center', display:'flex', flexDirection:'column', alignItems:'center', gap:1 }}>
                          <Movie sx={{ fontSize: 48, opacity: 0.5 }}/>
                          <Typography variant="body2">Please select a video below</Typography>
                      </Box>
                  )}
              </Box>

              {/* B. 播放控制區 */}
              <Box sx={{ p: 2, bgcolor: '#1e293b', borderBottom: '1px solid #334155', flexShrink: 0 }}>
                  <Grid container spacing={1} alignItems="center">
                    <Grid size={12}>
                        <Select
                            fullWidth
                            size="small"
                            value={selectedProjectId == null ? '' : String(selectedProjectId)}
                            onChange={(e) => {
                              const raw = String(e.target.value);
                              setSelectedProjectId(raw === '' ? null : Number(raw));
                            }}
                            displayEmpty
                            disabled={!loggedIn || projects.length === 0}
                            sx={{ color: 'white', bgcolor: '#0f172a', '.MuiOutlinedInput-notchedOutline': { borderColor: '#475569' } }}
                        >
                            <MenuItem value="" disabled>
                              {loggedIn ? '-- 選擇專案 --' : '-- 請先登入 --'}
                            </MenuItem>
                            {projects.map((p) => (
                              <MenuItem key={p.id} value={String(p.id)}>
                                {p.name}
                              </MenuItem>
                            ))}
                        </Select>
                    </Grid>
                    <Grid size={6}>
                        <Select
                            fullWidth
                            size="small"
                            value={statusFilter}
                            onChange={(e) => setStatusFilter(e.target.value)}
                            displayEmpty
                            disabled={selectedProjectId == null}
                            sx={{ color: 'white', bgcolor: '#0f172a', '.MuiOutlinedInput-notchedOutline': { borderColor: '#475569' } }}
                        >
                            <MenuItem value="">全部狀態</MenuItem>
                            {Object.entries(STATUS_LABELS).map(([k, label]) => (
                              <MenuItem key={k} value={k}>
                                {label}
                              </MenuItem>
                            ))}
                        </Select>
                    </Grid>
                    <Grid size={6}>
                        <Select
                            fullWidth
                            size="small"
                            value={assigneeFilter}
                            onChange={(e) => setAssigneeFilter(e.target.value)}
                            displayEmpty
                            disabled={selectedProjectId == null}
                            sx={{ color: 'white', bgcolor: '#0f172a', '.MuiOutlinedInput-notchedOutline': { borderColor: '#475569' } }}
                        >
                            <MenuItem value="">全部負責人</MenuItem>
                            <MenuItem value="__unassigned__">未指派</MenuItem>
                            {assigneeOptions.map((name) => (
                              <MenuItem key={name} value={name}>
                                {name}
                              </MenuItem>
                            ))}
                        </Select>
                    </Grid>
                    <Grid size={12}>
                        <Select 
                            fullWidth size="small" 
                            value={mediaFileName || ""} 
                            onChange={(e) => setMediaFileName(e.target.value)} 
                            displayEmpty
                            disabled={selectedProjectId == null}
                            sx={{ color: 'white', bgcolor: '#0f172a', '.MuiOutlinedInput-notchedOutline': { borderColor: '#475569' } }}
                        >
                            <MenuItem value="" disabled>-- 切換影片 --</MenuItem>
                            {filteredVideos.map((v: VideoRow) => (
                                <MenuItem key={v.path} value={v.path}>
                                  {v.name} · {STATUS_LABELS[v.status] ?? v.status}
                                  {v.assignee_real_name ? ` · ${v.assignee_real_name}` : ''}
                                </MenuItem>
                            ))}
                        </Select>
                    </Grid>
                    {videoRows.length > 0 && filteredVideos.length === 0 && (
                      <Grid size={12}>
                        <Alert severity="info" sx={{ py: 0.5, fontSize: '0.8rem' }}>
                          目前篩選下沒有符合的影片（資料庫共 {videoRows.length} 筆）。請改選「全部負責人」或調整狀態。
                        </Alert>
                      </Grid>
                    )}
                    {videoRows.length === 0 && selectedProjectId != null && loggedIn && (
                      <Grid size={12}>
                        <Alert severity="warning" sx={{ py: 0.5, fontSize: '0.8rem' }}>
                          此專案尚無可列出的媒體。請上傳檔案；若 data/ 已有案例，請確認資料庫內有對應任務（首次部署需執行 seed 掃描）。
                        </Alert>
                      </Grid>
                    )}
                    <Grid size={12} display="flex" gap={1} mt={1}>
                        <TextField 
                            fullWidth size="small" placeholder="Jump to (e.g. 1:20)" value={jumpInput} onChange={e=>setJumpInput(e.target.value)} onKeyDown={e=>e.key==='Enter'&&handleManualJump()}
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

              {/* C. 檔案列表區（較矮，內部捲動） */}
              <Box sx={{ flex: '1 1 0%', minHeight: 0, maxHeight: '32vh', overflowY: 'auto', p: 2, bgcolor: '#0f172a' }}>
                  
                  <Box sx={{ mb: 1.5, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <Typography variant="subtitle2" sx={{ color: '#94a3b8', display: 'flex', alignItems: 'center', gap: 1 }}>
                          <FolderOpen fontSize="small"/> 
                          {selectedCase ? 'Segment list (Chunks)' : 'Please select a video first'}
                      </Typography>
                      
                      {/* ★ 下載按鈕與重新整理 ★ */}
                      <Box>
                          <IconButton size="small" onClick={(e) => setDownloadAnchor(e.currentTarget)} disabled={!selectedCase}>
                              <Download fontSize="small" sx={{color: selectedCase ? '#38bdf8' : '#64748b'}}/>
                          </IconButton>
                          <IconButton size="small" onClick={() => { if(selectedCase) axios.get(`/api/temp/chunks?case=${selectedCase}`).then(res => setCaseChunks(res.data.files)); }}>
                              <Refresh fontSize="small" sx={{color:'#64748b'}}/>
                          </IconButton>
                      </Box>
                  </Box>

                  <List disablePadding>
                      {selectedCase && caseChunks.length === 0 && (
                          <Box sx={{textAlign:'center', mt:4, color:'#64748b'}}>
                              <Typography variant="body2">No segment files available for this video</Typography>
                          </Box>
                      )}

                      {caseChunks.map(f => {
                          const fileName = f.split('/').pop() || "";
                          const parts = fileName.split('_');
                          
                          let displayName = fileName;
                          let timeRange = "";
                          let chunkIndex = "";

                          if (parts.length >= 4) {
                              const idx = ["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th", "10th"];
                              const num = parseInt(parts[1]);
                              const numStr = (num >= 1 && num <= 10) ? idx[num - 1] : num;
                              
                              chunkIndex = `Segment ${numStr}`;
                              
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
                                                  
                                                  {isFlagged && <Chip label="Needs review" size="small" color="warning" sx={{height:20, fontSize:'0.7rem'}} icon={<Warning style={{fontSize:12}}/>} />}
                                                  {isEdited && <Chip label="Edited" size="small" color="success" sx={{height:20, fontSize:'0.7rem'}} icon={<CheckCircle style={{fontSize:12}}/>} />}
                                                  {isOriginal && <Chip label="Original" size="small" sx={{height:20, fontSize:'0.7rem', bgcolor:'transparent', border:'1px solid #64748b', color:'#94a3b8'}} />}
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
                           <Typography color="text.primary">Editing</Typography>
                      </Breadcrumbs>
                      
                      <Typography variant="h5" color="#1e293b" fontWeight={600} display="flex" alignItems="center" gap={1}>
                          <Edit fontSize="medium" color="primary"/>
                          {(() => {
                              const parts = selectedChunk.split('/').pop()?.split('_') || [];
                              const idx = ["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th", "10th"];
                              const num = parseInt(parts[1]);
                              const numStr = (num >= 1 && num <= 10) ? idx[num - 1] : num;
                              if (parts.length >= 2) return `Edit: Segment ${numStr}`;
                              return "Edit content";
                          })()}
                      </Typography>
                      
                      <Box sx={{mt: 2}}>
                        <ChunkTimepoints chunkTimepoints={chunkTimepoints} onJumpToTime={handleJumpToTime} fileType={fileType} />
                      </Box>
                  </Box>
              ) : (
                  <Box sx={{ textAlign: 'center', mt: 15, color: '#94a3b8' }}>
                      <Description sx={{ fontSize: 80, opacity: 0.1, mb: 2 }} />
                      <Typography variant="h6">Please select a segment</Typography>
                      <Typography variant="body2">Click a segment in the left list to start editing.</Typography>
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
                        onSyncEndTime={handleSyncEndTime}
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
          <Divider /><MenuItem onClick={() => { setAnchorEl(null); setIsNewSpeakerDialogOpen(true); }} sx={{color:'blue'}}><Add/> Add new...</MenuItem>
      </Menu>

      <Dialog open={isNewSpeakerDialogOpen} onClose={() => setIsNewSpeakerDialogOpen(false)}>
          <DialogTitle>Add speaker</DialogTitle>
          <DialogContent><TextField autoFocus margin="dense" label="Name" fullWidth value={newSpeakerName} onChange={(e) => setNewSpeakerName(e.target.value)} /></DialogContent>
          <DialogActions><Button onClick={() => setIsNewSpeakerDialogOpen(false)}>Cancel</Button><Button onClick={() => {if(activeSegmentIndex!==null && newSpeakerName) updateSpeaker(activeSegmentIndex, newSpeakerName); setIsNewSpeakerDialogOpen(false);}}>Confirm</Button></DialogActions>
      </Dialog>

      {/* ★ 完整的下載選單 (內嵌式) ★ */}
      <Menu 
          anchorEl={downloadAnchor} 
          open={Boolean(downloadAnchor)} 
          onClose={() => setDownloadAnchor(null)}
          PaperProps={{ sx: { bgcolor: '#1e293b', color: '#e2e8f0', border: '1px solid #334155', minWidth: 250 } }}
      >
          <Box sx={{ px: 2, py: 1, borderBottom: '1px solid #334155' }}>
              <Typography variant="subtitle2" color="#94a3b8">
                  Export full dataset (Full Export)
              </Typography>
          </Box>

          {/* 1. Golden Data (最重要) */}
          <MenuItem onClick={() => handleDownloadFile('edited')} sx={{ py: 1.5 }}>
              <ListItemIcon><CheckCircle fontSize="small" sx={{color:'#4ade80'}}/></ListItemIcon>
              <ListItemText 
                  primary="Human-corrected (Golden)" 
                  secondary="Final Training Data" 
                  primaryTypographyProps={{ fontWeight: 600, color: '#f8fafc' }}
                  secondaryTypographyProps={{ fontSize: '0.7rem', color: '#4ade80' }} 
              />
          </MenuItem>

          <Divider sx={{ my: 0.5, bgcolor: '#334155' }} />

          {/* 2. Processed Data */}
          <MenuItem onClick={() => handleDownloadFile('flagged')}>
              <ListItemIcon><Warning fontSize="small" sx={{color:'#fbbf24'}}/></ListItemIcon>
              <ListItemText primary="AI-flagged (Flagged)" secondary="Processed + LLM QA" secondaryTypographyProps={{fontSize:'0.7rem', color:'#94a3b8'}} />
          </MenuItem>
          <MenuItem onClick={() => handleDownloadFile('stitched')}>
              <ListItemIcon><Cable fontSize="small" sx={{color:'#c084fc'}}/></ListItemIcon>
              <ListItemText primary="Auto-stitched (Stitched)" secondary="Re-stitched Segments" secondaryTypographyProps={{fontSize:'0.7rem', color:'#94a3b8'}} />
          </MenuItem>
          <MenuItem onClick={() => handleDownloadFile('aligned')}>
              <ListItemIcon><AutoFixHigh fontSize="small" sx={{color:'#60a5fa'}}/></ListItemIcon>
              <ListItemText primary="Aligned (Aligned)" secondary="Whisper + Diarization" secondaryTypographyProps={{fontSize:'0.7rem', color:'#94a3b8'}} />
          </MenuItem>

          <Divider sx={{ my: 0.5, bgcolor: '#334155' }} />

          {/* 3. Raw Data */}
          <MenuItem onClick={() => handleDownloadFile('diar')}>
              <ListItemIcon><RecordVoiceOver fontSize="small" sx={{color:'#94a3b8'}}/></ListItemIcon>
              <ListItemText primary="Raw diarization (Raw Diar)" secondary="Speaker Timestamps Only" secondaryTypographyProps={{fontSize:'0.7rem', color:'#64748b'}} />
          </MenuItem>
          <MenuItem onClick={() => handleDownloadFile('whisper')}>
              <ListItemIcon><GraphicEq fontSize="small" sx={{color:'#94a3b8'}}/></ListItemIcon>
              <ListItemText primary="Raw ASR (Raw ASR)" secondary="Relative Timestamps" secondaryTypographyProps={{fontSize:'0.7rem', color:'#64748b'}} />
          </MenuItem>
      </Menu>

      <Dialog open={!loggedIn} disableEscapeKeyDown maxWidth="xs" fullWidth>
        <DialogTitle>登入或註冊</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 1 }}>
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button
              size="small"
              variant={authMode === 'login' ? 'contained' : 'outlined'}
              onClick={() => setAuthMode('login')}
            >
              登入
            </Button>
            <Button
              size="small"
              variant={authMode === 'register' ? 'contained' : 'outlined'}
              onClick={() => setAuthMode('register')}
            >
              註冊
            </Button>
          </Box>
          <TextField
            label="帳號"
            value={authUser}
            onChange={(e) => setAuthUser(e.target.value)}
            fullWidth
            autoComplete="username"
            sx={AUTH_DIALOG_TEXT_FIELD_SX}
          />
          <TextField
            label="密碼"
            type="password"
            value={authPass}
            onChange={(e) => setAuthPass(e.target.value)}
            fullWidth
            autoComplete={authMode === 'login' ? 'current-password' : 'new-password'}
            sx={AUTH_DIALOG_TEXT_FIELD_SX}
          />
          {authMode === 'register' && (
            <TextField
              label="顯示名稱"
              value={authRealName}
              onChange={(e) => setAuthRealName(e.target.value)}
              fullWidth
              sx={AUTH_DIALOG_TEXT_FIELD_SX}
            />
          )}
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          {authMode === 'login' ? (
            <Button variant="contained" onClick={handleLogin} disabled={!authUser || !authPass}>
              登入
            </Button>
          ) : (
            <Button
              variant="contained"
              onClick={handleRegister}
              disabled={!authUser || !authPass || !authRealName.trim()}
            >
              註冊
            </Button>
          )}
        </DialogActions>
      </Dialog>

      {/* 上傳與進度 Dialog */}
      <Dialog 
          open={isUploadOpen} 
          onClose={() => !isUploading && setIsUploadOpen(false)}
          maxWidth="sm"
          fullWidth
      >
          <DialogTitle sx={{ pb: 1 }}>
              Upload new case and run Pipeline
          </DialogTitle>
          
          <DialogContent sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 3 }}>
              {/* 自動填入檔名 */}
              <Autocomplete
                  freeSolo
                  options={existingTesters || []}
                  value={uploadCaseName}
                  onInputChange={(_, v) => setUploadCaseName(v)}
                  renderInput={(params) => (
                      <TextField 
                          {...params} 
                          label="Case name (Case Name)" 
                          fullWidth 
                          variant="outlined"
                          sx={{ mt: 1 }} 
                      />
                  )}
              />

              {!isUploading ? (
                  // 狀態 A: 等待上傳
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
                          display: 'flex', flexDirection: 'column', gap: 1,
                          '&:hover': { borderWidth: 2, borderColor: '#38bdf8', bgcolor: 'rgba(56, 189, 248, 0.1)' }
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
                              <Typography variant="h6" color="text.secondary">Select video file</Typography>
                              <Typography variant="caption" color="text.secondary">Supports .mp4, .wav</Typography>
                          </>
                      )}
                      <input 
                          type="file" hidden accept="video/*,audio/*" 
                          onChange={(e) => {
                              const file = e.target.files?.[0] || null;
                              setUploadFile(file);
                              if (file) {
                                  const fileNameWithoutExt = file.name.replace(/\.[^/.]+$/, "");
                                  setUploadCaseName(fileNameWithoutExt);
                              }
                          }} 
                      />
                  </Button>
              ) : (
                  // 狀態 B: 真實進度條
                  <Paper variant="outlined" sx={{ p: 3, bgcolor: '#f8fafc', borderColor: '#cbd5e1' }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', mb: 1, justifyContent: 'space-between' }}>
                          <Typography variant="subtitle1" fontWeight="bold" color="#0f172a">{currentStep}</Typography>
                          <Typography variant="h6" color="primary" fontWeight="bold">{Math.round(uploadProgress)}%</Typography>
                      </Box>
                      <Box sx={{ width: '100%', mr: 1 }}>
                          <LinearProgress 
                              variant="determinate" value={uploadProgress} 
                              sx={{ height: 10, borderRadius: 5, bgcolor: '#e2e8f0', '& .MuiLinearProgress-bar': { borderRadius: 5, bgcolor: '#3b82f6' } }}
                          />
                      </Box>
                      <Typography variant="caption" sx={{ display:'block', mt: 1.5, color: '#64748b' }}>Running AI processing on backend</Typography>
                  </Paper>
              )}
          </DialogContent>
          
          <DialogActions sx={{ px: 3, pb: 3 }}>
              <Button onClick={() => setIsUploadOpen(false)} disabled={isUploading} size="large">Cancel</Button>
              {!isUploading && (
                  <Button onClick={handleUploadConfirm} variant="contained" size="large" disabled={!uploadFile || !uploadCaseName || selectedProjectId == null} startIcon={<PlayCircle />} sx={{ px: 4 }}>Run Pipeline</Button>
              )}
          </DialogActions>
      </Dialog>

      <Snackbar open={toast.open} autoHideDuration={3000} onClose={() => setToast({...toast, open:false})}><Alert severity={toast.type} variant="filled">{toast.msg}</Alert></Snackbar>
    </Box>
  );
}

export default App;
import React from 'react';
import { Paper, Box, Typography, Divider, Button, CircularProgress } from '@mui/material';
import { Dashboard, CloudUpload, Save, Logout } from '@mui/icons-material';

interface Props {
  allSpeakers: string[];
  speakerMap: Record<string, string>;
  onRenameSpeaker: (original: string, newName: string) => void;
  onUploadOpen: () => void;
  onSave: () => void;
  hasUnsavedChanges: boolean;
  loading: boolean;
  onLogout?: () => void;
  onChangePassword?: () => void;
  onAdminOpen?: () => void;
  showAdminButton?: boolean;
}

export const TopBar: React.FC<Props> = ({
  allSpeakers,
  speakerMap,
  onRenameSpeaker,
  onUploadOpen,
  onSave,
  hasUnsavedChanges,
  loading,
  onLogout,
  onChangePassword,
  onAdminOpen,
  showAdminButton,
}) => {
  return (
    <Paper square elevation={0} sx={{ height: 60, px: 3, display: 'flex', alignItems: 'center', justifyContent: 'space-between', bgcolor: '#1e293b', borderBottom: '1px solid #334155', flexShrink: 0 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flex: 1, minWidth: 0 }}>
          <Dashboard sx={{ color: '#38bdf8', flexShrink: 0 }} />
          <Typography variant="h6" fontWeight="bold" sx={{ color: '#f8fafc', flexShrink: 0 }}>NeuroAI Editor</Typography>
          
          <Divider orientation="vertical" flexItem sx={{ bgcolor: '#475569', mx: 2, flexShrink: 0 }} />
          
          {/* Alias 編輯區：佔滿剩餘寬度並橫向捲動，右側留白避免最後一個被切 */}
          <Box sx={{ display: 'flex', gap: 2, overflowX: 'auto', alignItems: 'center', py: 1, pl: 0.5, pr: 1, flex: 1, minWidth: 0, '::-webkit-scrollbar': { height: 6 } }}>
              <Typography variant="caption" sx={{ color: '#64748b', fontWeight: 'bold', flexShrink: 0 }}>ALIAS:</Typography>
              {allSpeakers.map(spk => (
                  <Box
                      key={spk}
                      sx={{
                          display: 'flex',
                          alignItems: 'center',
                          bgcolor: '#334155',
                          borderRadius: 8,
                          pl: 2,
                          pr: 2,
                          py: 0.75,
                          border: '1px solid #475569',
                          flexShrink: 0,
                          overflow: 'visible',
                          minWidth: 'fit-content',
                      }}
                  >
                      <Typography variant="caption" sx={{ color: '#94a3b8', mr: 1.5, flexShrink: 0 }}>{spk}</Typography>
                      <input
                          value={speakerMap[spk] || ''}
                          onChange={(e) => onRenameSpeaker(spk, e.target.value)}
                          placeholder="Alias"
                          style={{
                              background: 'transparent',
                              border: 'none',
                              color: '#fff',
                              fontSize: '0.85rem',
                              minWidth: 88,
                              width: 88,
                              outline: 'none',
                              fontWeight: 'bold',
                              boxSizing: 'border-box',
                              padding: '2px 4px',
                          }}
                      />
                  </Box>
              ))}
              <Box sx={{ minWidth: 8, flexShrink: 0 }} />
          </Box>
      </Box>

      <Box sx={{ display: 'flex', gap: 2, flexShrink: 0 }}>
          {showAdminButton && onAdminOpen && (
            <Button
              variant="outlined"
              onClick={onAdminOpen}
              sx={{ borderColor: '#475569', color: '#94a3b8', '&:hover': { borderColor: '#a78bfa', color: '#c4b5fd' } }}
            >
              專案人員管理
            </Button>
          )}
          {onChangePassword && (
            <Button
              variant="outlined"
              onClick={onChangePassword}
              sx={{ borderColor: '#475569', color: '#94a3b8', '&:hover': { borderColor: '#fbbf24', color: '#fcd34d' } }}
            >
              修改密碼
            </Button>
          )}
          {onLogout && (
            <Button
              variant="outlined"
              startIcon={<Logout />}
              onClick={onLogout}
              sx={{ borderColor: '#475569', color: '#94a3b8', '&:hover': { borderColor: '#f87171', color: '#f87171' } }}
            >
              登出
            </Button>
          )}
          <Button 
            variant="outlined" 
            startIcon={<CloudUpload />} 
            onClick={onUploadOpen}
            sx={{ borderColor: '#475569', color: '#94a3b8', '&:hover': { borderColor: '#38bdf8', color: '#38bdf8' } }}
          >
              Upload video
          </Button>
          <Button 
            variant="contained" 
            color={hasUnsavedChanges ? "warning" : "primary"} 
            startIcon={loading ? <CircularProgress size={20} color="inherit"/> : <Save/>} 
            disabled={!hasUnsavedChanges || loading} 
            onClick={onSave}
          >
              {loading ? 'Saving...' : 'Save Changes'}
          </Button>
      </Box>
    </Paper>
  );
};
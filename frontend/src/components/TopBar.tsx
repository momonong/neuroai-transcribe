import React from 'react';
import { Paper, Box, Typography, Divider, Button, CircularProgress } from '@mui/material';
import { Dashboard, CloudUpload, Save } from '@mui/icons-material';

interface Props {
  allSpeakers: string[];
  speakerMap: Record<string, string>;
  onRenameSpeaker: (original: string, newName: string) => void;
  onUploadOpen: () => void;
  onSave: () => void;
  hasUnsavedChanges: boolean;
  loading: boolean;
}

export const TopBar: React.FC<Props> = ({ 
  allSpeakers, speakerMap, onRenameSpeaker, onUploadOpen, onSave, hasUnsavedChanges, loading 
}) => {
  return (
    <Paper square elevation={0} sx={{ height: 60, px: 3, display: 'flex', alignItems: 'center', justifyContent: 'space-between', bgcolor: '#1e293b', borderBottom: '1px solid #334155', flexShrink: 0 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Dashboard sx={{ color: '#38bdf8' }} />
          <Typography variant="h6" fontWeight="bold" sx={{ color: '#f8fafc' }}>NeuroAI Editor</Typography>
          
          <Divider orientation="vertical" flexItem sx={{ bgcolor: '#475569', mx: 2 }} />
          
          {/* Alias 編輯區 */}
          <Box sx={{ display: 'flex', gap: 2, overflowX: 'auto', maxWidth: '600px', alignItems: 'center', '::-webkit-scrollbar': { height: 4 } }}>
              <Typography variant="caption" sx={{ color: '#64748b', fontWeight: 'bold' }}>ALIAS:</Typography>
              {allSpeakers.map(spk => (
                  <Box key={spk} sx={{ display: 'flex', alignItems: 'center', bgcolor: '#334155', borderRadius: 8, px: 1.5, py: 0.5, border: '1px solid #475569' }}>
                      <Typography variant="caption" sx={{ color: '#94a3b8', mr: 1 }}>{spk}</Typography>
                      <input 
                          value={speakerMap[spk] || ''} 
                          onChange={(e) => onRenameSpeaker(spk, e.target.value)} 
                          placeholder="別名" 
                          style={{ background: 'transparent', border: 'none', color: '#fff', fontSize: '0.85rem', width: 60, outline: 'none', fontWeight: 'bold' }} 
                      />
                  </Box>
              ))}
          </Box>
      </Box>

      <Box sx={{ display: 'flex', gap: 2 }}>
          <Button 
            variant="outlined" 
            startIcon={<CloudUpload />} 
            onClick={onUploadOpen}
            sx={{ borderColor: '#475569', color: '#94a3b8', '&:hover': { borderColor: '#38bdf8', color: '#38bdf8' } }}
          >
              上傳影片
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
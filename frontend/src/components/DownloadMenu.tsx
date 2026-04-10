import { useState } from 'react';
import axios from 'axios';
import { 
    IconButton, Menu, MenuItem, ListItemIcon, ListItemText, 
    Divider, Tooltip, Typography, Box 
} from '@mui/material';
import { 
    Download, CheckCircle, Warning, 
    AutoFixHigh, GraphicEq, RecordVoiceOver, Cable 
} from '@mui/icons-material';

interface DownloadMenuProps {
    selectedCase: string | null;
}

export const DownloadMenu = ({ selectedCase }: DownloadMenuProps) => {
    const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);

    const handleOpen = (event: React.MouseEvent<HTMLElement>) => {
        setAnchorEl(event.currentTarget);
    };

    const handleClose = () => {
        setAnchorEl(null);
    };

    const handleDownload = async (type: string) => {
        if (!selectedCase) return;
        try {
            const response = await axios.get(`/api/export/${selectedCase}/${type}`, {
                responseType: 'blob',
            });
            
            // Create a temporary link to trigger the download
            const url = window.URL.createObjectURL(new Blob([response.data]));
            const link = document.createElement('a');
            link.href = url;
            
            // Extract filename from content-disposition if possible
            const contentDisposition = response.headers['content-disposition'];
            let filename = `${selectedCase}_FULL_${type}.json`;
            if (contentDisposition) {
                const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
                const matches = filenameRegex.exec(contentDisposition);
                if (matches != null && matches[1]) {
                    filename = matches[1].replace(/['"]/g, '');
                    // Handle UTF-8 encoded filename if present (filename*)
                    if (filename.startsWith("UTF-8''")) {
                        filename = decodeURIComponent(filename.substring(7));
                    }
                }
            }
            
            link.setAttribute('download', filename);
            document.body.appendChild(link);
            link.click();
            
            // Cleanup
            document.body.removeChild(link);
            window.URL.revokeObjectURL(url);
        } catch (error) {
            console.error('Download failed:', error);
            alert('下載失敗，請檢查權限或登入狀態。');
        }
        handleClose();
    };

    return (
        <>
            <Tooltip title={selectedCase ? "Download merged dataset" : "Please select a case first"}>
                <span>
                    <IconButton 
                        onClick={handleOpen} 
                        size="small" 
                        disabled={!selectedCase}
                        sx={{ 
                            color: selectedCase ? '#38bdf8' : '#64748b',
                            '&:hover': { bgcolor: 'rgba(56, 189, 248, 0.1)' }
                        }}
                    >
                        <Download fontSize="small" />
                    </IconButton>
                </span>
            </Tooltip>

            <Menu
                anchorEl={anchorEl}
                open={Boolean(anchorEl)}
                onClose={handleClose}
                PaperProps={{
                    elevation: 3,
                    sx: {
                        bgcolor: '#1e293b',
                        color: '#e2e8f0',
                        border: '1px solid #334155',
                        minWidth: 250
                    }
                }}
            >
                <Box sx={{ px: 2, py: 1, borderBottom: '1px solid #334155' }}>
                    <Typography variant="subtitle2" color="#94a3b8">
                        Export full dataset (Full Export)
                    </Typography>
                </Box>

                {/* 1. Golden Data */}
                <MenuItem onClick={() => handleDownload('edited')} sx={{ py: 1.5 }}>
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
                <MenuItem onClick={() => handleDownload('flagged')}>
                    <ListItemIcon><Warning fontSize="small" sx={{color:'#fbbf24'}}/></ListItemIcon>
                    <ListItemText primary="AI-flagged (Flagged)" secondary="Processed + LLM QA" secondaryTypographyProps={{fontSize:'0.7rem', color:'#94a3b8'}} />
                </MenuItem>
                <MenuItem onClick={() => handleDownload('stitched')}>
                    <ListItemIcon><Cable fontSize="small" sx={{color:'#c084fc'}}/></ListItemIcon>
                    <ListItemText primary="Auto-stitched (Stitched)" secondary="Re-stitched Segments" secondaryTypographyProps={{fontSize:'0.7rem', color:'#94a3b8'}} />
                </MenuItem>
                <MenuItem onClick={() => handleDownload('aligned')}>
                    <ListItemIcon><AutoFixHigh fontSize="small" sx={{color:'#60a5fa'}}/></ListItemIcon>
                    <ListItemText primary="Aligned (Aligned)" secondary="Whisper + Diarization" secondaryTypographyProps={{fontSize:'0.7rem', color:'#94a3b8'}} />
                </MenuItem>

                <Divider sx={{ my: 0.5, bgcolor: '#334155' }} />

                {/* 3. Raw Data */}
                <MenuItem onClick={() => handleDownload('diar')}>
                    <ListItemIcon><RecordVoiceOver fontSize="small" sx={{color:'#94a3b8'}}/></ListItemIcon>
                    <ListItemText primary="Raw diarization (Raw Diar)" secondary="Speaker Timestamps Only" secondaryTypographyProps={{fontSize:'0.7rem', color:'#64748b'}} />
                </MenuItem>
                <MenuItem onClick={() => handleDownload('whisper')}>
                    <ListItemIcon><GraphicEq fontSize="small" sx={{color:'#94a3b8'}}/></ListItemIcon>
                    <ListItemText primary="Raw ASR (Raw ASR)" secondary="Relative Timestamps" secondaryTypographyProps={{fontSize:'0.7rem', color:'#64748b'}} />
                </MenuItem>
            </Menu>
        </>
    );
};
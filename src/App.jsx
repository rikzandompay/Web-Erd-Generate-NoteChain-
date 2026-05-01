import React, { useState } from 'react';
import axios from 'axios';
import { Database, Download, Loader2, Sparkles, CheckCircle, FileWarning } from 'lucide-react';
import DragDropArea from './components/DragDropArea';

function App() {
  const [file, setFile] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  const handleFileSelected = (selectedFile) => {
    setFile(selectedFile);
    setError('');
    setSuccess(false);
  };

  const handleGenerate = async () => {
    if (!file) {
      setError('Please select a file first.');
      return;
    }

    setIsLoading(true);
    setError('');
    setSuccess(false);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await axios.post('/api/generate', formData, {
        responseType: 'blob', // Important: receive response as binary blob for download
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      // Handle successful download
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;

      // Extract filename from headers if possible, or fallback
      const contentDisposition = response.headers['content-disposition'];
      let filename = file.name.replace('.sql', '_erd.drawio');
      if (contentDisposition) {
        const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/);
        if (filenameMatch && filenameMatch.length === 2) {
          filename = filenameMatch[1];
        }
      }

      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);

      setSuccess(true);
    } catch (err) {
      console.error('Error generating ERD:', err);

      // Parse error from Blob response if it's a 4xx HTTP error
      if (err.response && err.response.data instanceof Blob) {
        const errorText = await err.response.data.text();
        try {
          const errorJson = JSON.parse(errorText);
          setError(errorJson.detail || 'An error occurred during generation.');
        } catch {
          setError('Failed to process the SQL file.');
        }
      } else {
        setError(err.message || 'Network error connecting to the server.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen relative overflow-hidden flex flex-col items-center justify-center p-6">
      {/* Background Blobs */}
      <div className="bg-blob blob-1"></div>
      <div className="bg-blob blob-2"></div>

      <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-20 pointer-events-none mix-blend-overlay"></div>

      {/* Main Container */}
      <main className="w-full max-w-4xl relative z-10 animate-fade-in glass p-8 md:p-12 rounded-[2rem] shadow-2xl">

        {/* Header Section */}
        <header className="text-center space-y-4 mb-10">
          <div className="inline-flex items-center justify-center p-4 bg-blue-500/10 rounded-2xl border border-blue-500/20 shadow-[0_0_30px_rgba(59,130,246,0.15)] mb-2">
            <Database size={40} className="text-blue-400 animate-float" />
          </div>
          <h1 className="text-4xl md:text-6xl font-extrabold tracking-tight">
            SQL to <span className="text-gradient">ERD Generator</span>
          </h1>
          <p className="text-gray-400 text-lg md:text-xl max-w-2xl mx-auto font-medium">
            Buat ERD Note Chain lebih cepat dengan <code className="bg-dark-800 px-2 py-1 rounded text-blue-300 font-mono text-sm border border-white/5">ERD GENERATOR By Rikzan</code>Dibuat untuk menggantikan proses menggambar manual yang repetitif menjadi alur kerja drag-and-drop yang instan.
          </p>
        </header>

        {/* Upload Area */}
        <DragDropArea
          onFileSelected={handleFileSelected}
          isLoading={isLoading}
          file={file}
        />

        {/* Action Button Section */}
        <div className="flex flex-col items-center mt-8 space-y-4">
          <button
            onClick={handleGenerate}
            disabled={!file || isLoading}
            className={`
              relative overflow-hidden group flex items-center justify-center gap-3 w-full max-w-sm py-4 px-8 rounded-2xl font-semibold text-lg transition-all duration-300
              ${!file || isLoading
                ? 'bg-dark-700 text-gray-400 cursor-not-allowed border border-white/5'
                : 'bg-primary-600 text-white hover:bg-primary-500 shadow-[0_0_40px_rgba(37,99,235,0.3)] hover:shadow-[0_0_60px_rgba(59,130,246,0.4)] hover:-translate-y-1'
              }
            `}
          >
            {/* Button Shine Effect */}
            {file && !isLoading && (
              <div className="absolute inset-0 -translate-x-full group-hover:animate-[shimmer_1.5s_infinite] bg-gradient-to-r from-transparent via-white/20 to-transparent skew-x-12" />
            )}

            {isLoading ? (
              <>
                <Loader2 size={24} className="animate-spin" />
                <span>Parsing Schema...</span>
              </>
            ) : (
              <>
                <Sparkles size={24} className={file ? "animate-pulse" : ""} />
                <span>Generate Diagram</span>
              </>
            )}
          </button>

          {/* Status Messages */}
          <div className="h-14 flex items-center justify-center">
            {error && (
              <div className="flex items-center gap-2 text-red-400 bg-red-400/10 px-4 py-2 rounded-xl animate-fade-in border border-red-400/20">
                <FileWarning size={18} />
                <span className="font-medium text-sm">{error}</span>
              </div>
            )}

            {success && (
              <div className="flex items-center gap-2 text-green-400 bg-green-400/10 px-4 py-2 rounded-xl animate-fade-in border border-green-400/20">
                <CheckCircle size={18} />
                <span className="font-medium text-sm">Success! Your .drawio file is downloading.</span>
              </div>
            )}
          </div>
        </div>

      </main>

      {/* Footer */}
      <footer className="mt-12 text-center text-gray-500 text-sm font-medium relative z-10 w-full animate-fade-in">
        <p>Development by Rikzan • No server storage • Native mxGraph support</p>
      </footer>

      {/* Tailwind Custom Animations for App */}
      <style dangerouslySetInnerHTML={{
        __html: `
        @keyframes shimmer {
          100% { transform: translateX(200%); }
        }
      `}} />
    </div>
  );
}

export default App;

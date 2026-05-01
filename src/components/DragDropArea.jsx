// frontend/src/components/DragDropArea.jsx
import React, { useRef, useState } from 'react';
import { UploadCloud, FileType, CheckCircle, XCircle } from 'lucide-react';

export default function DragDropArea({ onFileSelected, isLoading, file }) {
  const [isDragActive, setIsDragActive] = useState(false);
  const [error, setError] = useState('');
  const inputRef = useRef(null);

  const handleDragEnter = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!isLoading) setIsDragActive(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const processFile = (file) => {
    setError('');
    const fileName = file.name.toLowerCase();
    
    // Check if file has .sql extension
    if (!fileName.endsWith('.sql')) {
      setError('Please upload a valid .sql file.');
      return;
    }

    onFileSelected(file);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);
    
    if (isLoading) return;

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      if (e.dataTransfer.files.length > 1) {
        setError('Please upload only one file at a time.');
        return;
      }
      processFile(e.dataTransfer.files[0]);
      e.dataTransfer.clearData();
    }
  };

  const handleChange = (e) => {
    e.preventDefault();
    if (isLoading) return;
    
    if (e.target.files && e.target.files.length > 0) {
      processFile(e.target.files[0]);
    }
  };

  const onButtonClick = () => {
    if (!isLoading) {
      inputRef.current?.click();
    }
  };

  return (
    <div className="w-full max-w-2xl mx-auto my-8">
      <div 
        className={`relative group rounded-3xl p-1 transition-all duration-500
          ${isDragActive ? 'bg-gradient-to-r from-blue-500 to-indigo-500' : 'bg-white/5 hover:bg-white/10'}
          ${isLoading ? 'opacity-70 cursor-not-allowed' : 'cursor-pointer'}
        `}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        onClick={onButtonClick}
      >
        <div className={`
          glass-card rounded-[22px] flex flex-col items-center justify-center p-12 text-center h-80
          transition-all duration-300
          ${isDragActive ? 'border-transparent scale-[0.99] bg-dark-800/80' : 'border-white/10 hover:border-blue-500/50'}
        `}>
          <input
            ref={inputRef}
            type="file"
            className="hidden"
            accept=".sql"
            onChange={handleChange}
            disabled={isLoading}
          />
          
          <div className="relative mb-6">
            <div className={`absolute inset-0 bg-blue-500 blur-2xl rounded-full transition-opacity duration-500
              ${isDragActive ? 'opacity-40' : 'opacity-0 group-hover:opacity-20'}
            `} />
            
            {!file ? (
              <UploadCloud 
                size={80} 
                className={`relative z-10 transition-transform duration-500 
                  ${isDragActive ? 'text-blue-400 scale-110 -translate-y-2 animate-float' : 'text-gray-400 group-hover:text-blue-400 group-hover:scale-105 group-hover:-translate-y-1'}
                `} 
              />
            ) : (
              <div className="relative z-10">
                <FileType size={80} className="text-blue-400" />
                <div className="absolute -bottom-2 -right-2 bg-gradient-to-br from-green-400 to-emerald-600 rounded-full p-1 shadow-lg ring-4 ring-dark-800">
                  <CheckCircle size={20} className="text-white bg-transparent rounded-full" />
                </div>
              </div>
            )}
          </div>

          {!file ? (
            <div className="space-y-3">
              <h3 className="text-2xl font-semibold text-white tracking-tight">
                {isDragActive ? 'Drop your SQL file here' : 'Select or drag SQL file'}
              </h3>
              <p className="text-gray-400 text-base max-w-[280px] mx-auto leading-relaxed">
                Upload your <span className="text-blue-400 font-medium">.sql</span> file containing CREATE TABLE statements to generate an ERD.
              </p>
            </div>
          ) : (
            <div className="space-y-4 animate-fade-in w-full">
              <div className="flex flex-col items-center gap-2">
                <p className="text-xl font-medium text-white truncate max-w-sm" title={file.name}>
                  {file.name}
                </p>
                <div className="px-3 py-1 bg-white/10 rounded-full border border-white/5">
                  <span className="text-sm text-gray-400 whitespace-nowrap">
                    {(file.size / 1024).toFixed(1)} KB
                  </span>
                </div>
              </div>
              {!isLoading && (
                <p className="text-sm text-blue-400 hover:text-blue-300 transition-colors">
                  Click to choose a different file
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="mt-4 flex items-center justify-center gap-2 text-red-400 bg-red-400/10 border border-red-400/20 py-3 px-4 rounded-2xl animate-fade-in">
          <XCircle size={18} />
          <p className="text-sm font-medium">{error}</p>
        </div>
      )}
    </div>
  );
}

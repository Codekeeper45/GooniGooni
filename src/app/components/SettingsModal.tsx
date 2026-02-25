import React, { useState } from "react";
import { Key, ShieldAlert, X } from "lucide-react";

export function SettingsModal({ onClose }: { onClose: () => void }) {
  const [apiKey, setApiKey] = useState(() => localStorage.getItem("mg_api_key") ?? "");
  const [adminKey, setAdminKey] = useState(() => localStorage.getItem("mg_admin_key") ?? "");

  const handleSave = () => {
    localStorage.setItem("mg_api_key", apiKey.trim());
    localStorage.setItem("mg_admin_key", adminKey.trim());
    onClose();
    // For simplicity, reload to apply new keys to the global vars
    window.location.reload();
  };

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-[9999] backdrop-blur-sm">
      <div className="bg-gray-900 border border-gray-800 rounded-2xl w-full max-w-md overflow-hidden flex flex-col shadow-2xl">
        <div className="flex items-center justify-between p-6 border-b border-gray-800">
          <div className="flex items-center gap-2">
            <Key className="w-5 h-5 text-indigo-400" />
            <h2 className="text-lg font-semibold text-gray-100 m-0">API Configuration</h2>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>
        
        <div className="p-6 flex flex-col gap-5">
          <div className="flex bg-indigo-500/10 border border-indigo-500/20 p-3 rounded-xl gap-3">
            <ShieldAlert className="w-5 h-5 text-indigo-400 flex-shrink-0 mt-0.5" />
            <p className="text-sm text-indigo-200/80 leading-relaxed m-0">
              Your keys are stored securely in your browser's Local Storage. They are never sent anywhere except directly to your backend server.
            </p>
          </div>
          
          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium text-gray-300">Gooni API Key</label>
            <input 
              type="password" 
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="Enter your API Key"
              className="bg-gray-950 border border-gray-800 rounded-xl px-4 py-3 text-sm text-gray-200 outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/50 transition-all font-mono"
            />
            <span className="text-xs text-gray-500">Required for generating media and viewing results.</span>
          </div>
          
          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium text-gray-300">Admin Key (Optional)</label>
            <input 
              type="password" 
              value={adminKey}
              onChange={(e) => setAdminKey(e.target.value)}
              placeholder="Enter your Admin Key"
              className="bg-gray-950 border border-gray-800 rounded-xl px-4 py-3 text-sm text-gray-200 outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/50 transition-all font-mono"
            />
            <span className="text-xs text-gray-500">Required only for accessing the Admin panel.</span>
          </div>
        </div>

        <div className="p-6 border-t border-gray-800 flex justify-end gap-3 bg-gray-900/50">
          <button 
            onClick={onClose}
            className="px-5 py-2.5 rounded-xl text-sm font-medium text-gray-300 hover:text-white transition-colors"
          >
            Cancel
          </button>
          <button 
            onClick={handleSave}
            className="px-5 py-2.5 rounded-xl text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-500 shadow-lg shadow-indigo-500/20 transition-all"
          >
            Save Keys
          </button>
        </div>
      </div>
    </div>
  );
}

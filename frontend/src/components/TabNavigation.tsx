import React from 'react';
import { Bot, Calendar, Sparkles, BarChart3, Settings } from 'lucide-react';

interface TabNavigationProps {
  activeTab: number;
  setActiveTab: (tab: number) => void;
}

export const TabNavigation: React.FC<TabNavigationProps> = ({ activeTab, setActiveTab }) => {
  const tabs = [
    { id: 1, label: 'Emploi du Temps', icon: Calendar },
    { id: 2, label: 'Simulateur SMA', icon: Bot },
    { id: 3, label: 'Assistant Hybride', icon: Sparkles },
    { id: 4, label: 'Analytics ROI & Green IT', icon: BarChart3 },
    { id: 5, label: 'Gestion Ressources', icon: Settings },
  ];

  return (
    <nav className="bg-white border-b border-slate-200 shadow-sm sticky top-0 z-30">
      <div className="max-w-7xl mx-auto px-4 flex overflow-x-auto space-x-1 custom-scrollbar">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center space-x-2 px-4 py-3 text-sm font-medium border-b-2 whitespace-nowrap transition-colors ${
                isActive
                  ? 'border-ucac-orange text-ucac-orange bg-orange-50/50'
                  : 'border-transparent text-slate-600 hover:text-ucac-navy hover:border-slate-300'
              }`}
            >
              <Icon className={`w-4 h-4 ${isActive ? 'text-ucac-orange' : 'text-slate-400'}`} />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
};
"use client";

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  ReactNode,
} from "react";
import {
  translations,
  LanguageCode,
  TranslationKey,
} from "../i18n/translations";

interface LanguageContextType {
  currentLang: LanguageCode;
  setLanguage: (lang: LanguageCode) => void;
  t: (key: TranslationKey) => string;
}

const LanguageContext = createContext<LanguageContextType | undefined>(
  undefined
);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [currentLang, setCurrentLang] = useState<LanguageCode>("ko");

  useEffect(() => {
    // Load from localStorage if available
    const saved = localStorage.getItem("app_lang") as LanguageCode;
    if (saved && translations[saved]) {
      setCurrentLang(saved);
    }
  }, []);

  const setLanguage = (lang: LanguageCode) => {
    setCurrentLang(lang);
    localStorage.setItem("app_lang", lang);
  };

  const t = (key: TranslationKey): string => {
    return translations[currentLang][key] || translations["ko"][key] || key;
  };

  return (
    <LanguageContext.Provider value={{ currentLang, setLanguage, t }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  const context = useContext(LanguageContext);
  if (context === undefined) {
    throw new Error("useLanguage must be used within a LanguageProvider");
  }
  return context;
}

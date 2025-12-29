"use client";

import { useState, useEffect, useRef } from "react";
import Image from "next/image";
import axios from "axios";
import {
  Upload,
  FileText,
  CheckCircle,
  AlertTriangle,
  Download,
  User as UserIcon,
  LogIn,
  LogOut,
  Scan,
  ShieldCheck,
  Brain,
  Search,
  Check,
  Home as HomeIcon,
  Briefcase,
  Clock, // History Icon
  Trash2,
  Loader2,
  UserPlus,
} from "lucide-react";

import { useLanguage } from "./contexts/LanguageContext";
import { translations, LanguageCode } from "./i18n/translations";
import SignupModal from "../components/SignupModal";

export default function Home() {
  const { t, currentLang, setLanguage } = useLanguage();

  // Screens: 'login' | 'service_select' | 'upload' | 'analyzing' | 'result'
  const [view, setView] = useState<
    | "login"
    | "service_select"
    | "upload"
    | "analyzing"
    | "result"
    | "history"
    | "profile"
  >("login");

  // Auth State
  const [user, setUser] = useState<any>(null); // {email, token}

  // Timer Ref for cleanup
  const timersRef = useRef<NodeJS.Timeout[]>([]);

  // Upload State
  const [contractFile, setContractFile] = useState<File | null>(null);
  const [registryFile, setRegistryFile] = useState<File | null>(null);

  // Analysis State
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<any>(null);
  const [abortController, setAbortController] =
    useState<AbortController | null>(null);
  const [viewerTab, setViewerTab] = useState<"contract" | "registry">(
    "contract"
  );
  const [selectedService, setSelectedService] = useState<"rent" | "labor">(
    "rent"
  );

  // Hydration Fix
  const [isMounted, setIsMounted] = useState(false);
  useEffect(() => {
    setIsMounted(true);
  }, []);

  // Animation State
  const [progressStep, setProgressStep] = useState(0); // 0: Start, 1: OCR, 2: Rule, 3: PII, 4: AI

  // Clear error when changing views or services
  useEffect(() => {
    setError(null);
  }, [view, selectedService]);

  // Persist Login
  useEffect(() => {
    const stored = localStorage.getItem("user_session");
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        if (parsed?.token) {
          setUser(parsed);
          setView("service_select");
        }
      } catch (e) {
        console.error("Failed to parse session", e);
        localStorage.removeItem("user_session");
      }
    }
  }, []);

  // History State
  const [historyList, setHistoryList] = useState<any[]>([]);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);

  // Signup Modal State
  const [isSignupOpen, setIsSignupOpen] = useState(false);

  // Login Inputs & Loading
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [isDeletingAccount, setIsDeletingAccount] = useState(false);

  // --- Auth Handlers ---
  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!loginEmail || !loginPassword) {
      alert("이메일과 비밀번호를 입력해주세요.");
      return;
    }

    setIsLoggingIn(true);
    try {
      const formData = new FormData();
      formData.append("username", loginEmail);
      formData.append("password", loginPassword);

      const res = await axios.post(
        "http://localhost:8000/api/v1/auth/login",
        formData
      );

      const token = res.data.access_token;

      // Fetch User Info to get Name
      const userRes = await axios.get("http://localhost:8000/api/v1/auth/me", {
        headers: { Authorization: `Bearer ${token}` },
      });

      const userInfo = {
        email: userRes.data.email,
        name: userRes.data.full_name || "회원",
        token: token,
      };

      setUser(userInfo);
      localStorage.setItem("user_session", JSON.stringify(userInfo));

      setView("service_select");
    } catch (err: any) {
      console.error("Login Failed", err);
      const msg = err.response?.data?.detail || "로그인에 실패했습니다.";
      alert(msg);
    } finally {
      setIsLoggingIn(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("user_session");
    setUser(null);
    setView("login");
    setLoginEmail("");
    setLoginPassword("");
    setContractFile(null);
    setRegistryFile(null);
    setResult(null);
  };

  const goHome = () => {
    if (user) {
      setView("service_select");
      setResult(null);
      setContractFile(null);
      setRegistryFile(null);
    } else {
      setView("login");
    }
  };

  // --- Analysis Handlers ---
  const handleAnalyze = async () => {
    // Validate based on service type
    if (selectedService === "rent") {
      if (!contractFile || !registryFile) {
        alert("두 파일을 모두 선택해주세요.");
        return;
      }
    } else {
      if (!contractFile) {
        alert("근로계약서를 선택해주세요.");
        return;
      }
    }

    // Start Analysis UI
    setView("analyzing");
    setProgressStep(0);
    setError(null);
    setResult(null);

    // Mock Progress Animation (Sequence of 4 steps)
    // Clear existing timers
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];

    // Mock Progress Animation (Sequence of 4 steps)
    timersRef.current.push(setTimeout(() => setProgressStep(1), 1000)); // OCR Start
    timersRef.current.push(setTimeout(() => setProgressStep(2), 2500)); // Rule Check
    timersRef.current.push(setTimeout(() => setProgressStep(3), 4000)); // PII Masking
    timersRef.current.push(setTimeout(() => setProgressStep(4), 5500)); // AI Generation

    const formData = new FormData();
    formData.append("contract_file", contractFile);
    formData.append("registry_file", registryFile);
    formData.append("target_language", currentLang);

    const controller = new AbortController();
    setAbortController(controller);

    try {
      // Endpoint Switching
      const endpoint =
        selectedService === "labor"
          ? "http://localhost:8000/api/v1/analyze/labor"
          : "http://localhost:8000/api/v1/analyze";

      const response = await axios.post(endpoint, formData, {
        headers: {
          "Content-Type": "multipart/form-data",
          Authorization: `Bearer ${user?.token}`,
        },
        signal: controller.signal,
      });

      // Fix: Backend returns 200 OK even on logic error (success=false).
      // We must check this flag to trigger error handling.
      if (!response.data.success) {
        // Throw object mimicking axios error structure for the catch block
        throw { response };
      }

      // Wait a bit if API was too fast, to show animation
      // Wait a bit if API was too fast, to show animation
      timersRef.current.push(
        setTimeout(() => {
          // Only set result if we are still in analyzing view (not cancelled)
          setResult(response.data.data);
          setViewerTab("contract");
          setView((prev) => (prev === "analyzing" ? "result" : prev));
        }, 6000)
      ); // Ensure at least 6s total animation
    } catch (err: any) {
      // Clear timers immediately on error
      timersRef.current.forEach(clearTimeout);
      timersRef.current = [];

      if (axios.isCancel(err)) {
        console.log("Request canceled");
        return;
      }
      console.error(err);

      // Construct safe error object
      const safeError = err.response?.data?.error || {
        message: "알 수 없는 오류가 발생했습니다.",
      };
      // Ensure message is string
      if (typeof safeError.message !== "string") {
        safeError.message = JSON.stringify(safeError.message);
      }

      setError(safeError);

      setError(safeError);

      // Remove auto-redirect to prevent blank screen / confusion
      // The user will see the error state in the analyzing view
    }
  };

  const handleStopAnalysis = async () => {
    if (abortController) {
      setIsCancelling(true);
      abortController.abort();

      // UX Wait: Give backend time to process disconnection
      await new Promise((resolve) => setTimeout(resolve, 2000));

      setAbortController(null);
      setIsCancelling(false);
      setView("service_select");
      setProgressStep(0);
    }
  };

  const fetchHistory = async () => {
    if (!user?.token) return;
    if (isHistoryLoading) return; // Prevent double click

    setIsHistoryLoading(true);
    try {
      // Added trailing slash to avoid 307 Redirect issues
      const res = await axios.get("http://localhost:8000/api/v1/history/", {
        headers: { Authorization: `Bearer ${user.token}` },
      });
      setHistoryList(res.data);
    } catch (err: any) {
      console.error(err);
      const msg = err.response?.data?.detail || "히스토리 불러오기 실패";
      alert(msg);
    } finally {
      setIsHistoryLoading(false);
    }
  };

  const handleDeleteHistory = async (
    e: React.MouseEvent,
    analysisId: string
  ) => {
    e.stopPropagation(); // Prevent card click execution
    if (!user?.token) return;
    if (!confirm(t("delete_confirm"))) return;

    try {
      await axios.delete(`http://localhost:8000/api/v1/history/${analysisId}`, {
        headers: { Authorization: `Bearer ${user.token}` },
      });
      // Remove from list locally
      setHistoryList((prev) => prev.filter((item) => item.id !== analysisId));
      alert(t("delete_success"));
    } catch (err) {
      console.error("Failed to delete history:", err);
      alert(t("delete_fail"));
    }
  };

  const handleProfileClick = async () => {
    await fetchHistory();
    setView("profile");
  };

  const handleDeleteAccount = async () => {
    if (!confirm(t("delete_account_confirm"))) return;
    if (!user?.token) return;

    setIsDeletingAccount(true);
    try {
      // Artificial delay for UX (1.5s)
      await new Promise((resolve) => setTimeout(resolve, 1500));

      await axios.delete("http://localhost:8000/api/v1/auth/me", {
        headers: { Authorization: `Bearer ${user.token}` },
      });
      alert(t("delete_account_success"));
      handleLogout();
    } catch (err) {
      console.error("Delete Account Failed", err);
      alert(t("delete_account_fail"));
    } finally {
      setIsDeletingAccount(false);
    }
  };

  return (
    <div className="min-h-screen bg-blue-50 flex flex-col font-sans text-gray-900">
      {/* Full Screen Loading Overlay */}
      {(isHistoryLoading || isCancelling || isDeletingAccount) && (
        <div className="fixed inset-0 bg-black/50 z-[9999] flex flex-col items-center justify-center backdrop-blur-sm">
          <Loader2 className="w-16 h-16 text-white animate-spin mb-4" />
          <span className="text-white text-xl font-bold">
            {isCancelling
              ? "분석 중단 중..."
              : isDeletingAccount
              ? "회원 탈퇴 처리 중..."
              : "로딩 중..."}
          </span>
        </div>
      )}

      {/* --- Header --- */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between sticky top-0 z-50 shadow-sm">
        <div
          className="flex items-center gap-3 cursor-pointer transition-opacity hover:opacity-80"
          onClick={goHome}
        >
          <Image
            src="/logo.png"
            alt="CheckMate Logo"
            width={48}
            height={48}
            className="w-12 h-12 object-contain"
          />
          <span className="bg-gradient-to-r from-blue-500 via-indigo-600 to-violet-900 bg-clip-text text-transparent font-bold text-2xl tracking-tight font-[family-name:var(--font-outfit)] mt-1">
            CheckMate
          </span>
        </div>

        <div className="flex items-center gap-4">
          {/* Language Switcher */}
          <select
            value={currentLang}
            onChange={(e) => setLanguage(e.target.value as LanguageCode)}
            disabled={view === "analyzing" || view === "result"}
            className={`px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-lg text-base font-bold text-gray-700 outline-none focus:ring-2 focus:ring-indigo-500 transition-opacity ${
              view === "analyzing" || view === "result"
                ? "opacity-50 cursor-not-allowed"
                : ""
            }`}
          >
            <option value="ko">🇰🇷 한국어</option>
            <option value="en">🇺🇸 English</option>
            <option value="ne">🇳🇵 नेपाली (Nepali)</option>
            <option value="km">🇰🇭 ខ្មែរ (Khmer)</option>
            <option value="id">🇮🇩 Indonesia</option>
            <option value="vi">🇻🇳 Tiếng Việt</option>
            <option value="my">🇲🇲 ဗမာ (Burmese)</option>
            <option value="th">🇹🇭 ไทย (Thai)</option>
          </select>

          {user ? (
            <>
              <div
                className="flex items-center gap-2 px-4 py-2 bg-gray-50 rounded-full border border-gray-100 cursor-pointer hover:bg-gray-100 transition-colors"
                onClick={handleProfileClick}
              >
                <UserIcon className="w-5 h-5 text-gray-500" />
                <span className="font-medium text-gray-700">
                  {user.name} 님
                </span>
              </div>

              <button
                onClick={handleLogout}
                className="flex items-center gap-2 text-sm font-medium text-gray-400 hover:text-red-500 transition-colors"
              >
                <LogOut className="w-4 h-4" />
                {t("logout")}
              </button>
            </>
          ) : (
            <button
              onClick={() => setIsSignupOpen(true)}
              className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-blue-500 via-indigo-600 to-violet-900 hover:opacity-90 text-white rounded-lg transition shadow-md shadow-indigo-200"
            >
              <UserPlus className="w-4 h-4" />
              {t("signup_btn")}
            </button>
          )}
        </div>
      </header>

      {/* --- Main Content --- */}
      <main
        className="flex-1 flex flex-col relative overflow-hidden"
        suppressHydrationWarning
      >
        {/* LOGIN VIEW */}
        {view === "login" && (
          <div className="flex-1 flex flex-col items-center justify-center p-4 bg-gradient-to-br from-indigo-50 via-white to-blue-50">
            <div className="bg-white p-14 rounded-3xl shadow-2xl border border-indigo-50 max-w-lg w-full text-center">
              <div className="flex justify-center mb-2">
                <Image
                  src="/logo.png"
                  alt="CheckMate Logo"
                  width={192}
                  height={192}
                  className="w-48 h-48 object-contain"
                />
              </div>
              <h1 className="text-3xl font-bold mb-2 bg-gradient-to-r from-blue-500 via-indigo-600 to-violet-900 bg-clip-text text-transparent tracking-tight font-[family-name:var(--font-outfit)]">
                {t("login_title")}
              </h1>
              <p className="text-gray-500 mb-8 text-base whitespace-pre-line">
                {t("login_desc")}
              </p>

              <form onSubmit={handleLogin} className="space-y-6">
                <div className="text-left">
                  <label className="block text-sm font-bold text-gray-700 mb-2 ml-1">
                    Email
                  </label>
                  <input
                    type="email"
                    value={loginEmail}
                    onChange={(e) => setLoginEmail(e.target.value)}
                    placeholder="user@example.com"
                    className="w-full px-5 py-4 bg-gray-50 border border-gray-200 rounded-xl text-base focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-all"
                  />
                </div>
                <div className="text-left">
                  <label className="block text-sm font-bold text-gray-700 mb-2 ml-1">
                    Password
                  </label>
                  <input
                    type="password"
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    placeholder="비밀번호 입력"
                    className="w-full px-5 py-4 bg-gray-50 border border-gray-200 rounded-xl text-base focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-all"
                  />
                </div>
                <button
                  type="submit"
                  disabled={isLoggingIn}
                  className="w-full py-4 bg-gradient-to-r from-blue-500 via-indigo-600 to-violet-900 hover:opacity-90 disabled:opacity-70 text-white text-lg font-bold rounded-xl shadow-lg shadow-indigo-200 transition-all transform hover:-translate-y-0.5 mt-2 flex items-center justify-center gap-2"
                >
                  {isLoggingIn ? (
                    <>
                      <Loader2 className="w-5 h-5 animate-spin" />
                      <span>{t("login_btn").replace("하기", " 중...")}</span>
                    </>
                  ) : (
                    t("login_btn")
                  )}
                </button>
              </form>
              <p className="mt-8 text-sm text-gray-400">{t("demo_account")}</p>
            </div>
          </div>
        )}

        {/* SERVICE SELECT VIEW */}
        {view === "service_select" && (
          <div className="flex-1 flex flex-col items-center justify-center p-4">
            <div className="text-center mb-12">
              <h2 className="text-3xl font-bold text-gray-900 mb-4">
                {t("select_service_title")}
              </h2>
            </div>

            <div className="flex flex-col md:flex-row gap-8 max-w-4xl w-full">
              {/* Rent Contract Card */}
              <div
                onClick={() => {
                  setSelectedService("rent");
                  setView("upload");
                }}
                className="flex-1 bg-white p-8 rounded-3xl border border-gray-100 shadow-xl hover:shadow-2xl hover:border-indigo-200 transition-all cursor-pointer group transform hover:-translate-y-1"
              >
                <div className="w-16 h-16 bg-indigo-50 rounded-2xl flex items-center justify-center mb-6 group-hover:bg-indigo-600 transition-colors">
                  <HomeIcon className="w-8 h-8 text-indigo-600 group-hover:text-white transition-colors" />
                </div>
                <h3 className="text-2xl font-bold text-gray-900 mb-3 group-hover:text-indigo-700">
                  {t("service_rent_title")}
                </h3>
                <p className="text-gray-500 leading-relaxed">
                  {t("service_rent_desc")}
                </p>
              </div>

              {/* Labor Contract Card */}
              <div
                onClick={() => {
                  setSelectedService("labor");
                  setView("upload");
                }}
                className="flex-1 bg-white p-8 rounded-3xl border border-gray-100 shadow-xl hover:shadow-2xl hover:border-gray-200 transition-all cursor-pointer group transform hover:-translate-y-1 relative overflow-hidden"
              >
                <div className="w-16 h-16 bg-green-50 rounded-2xl flex items-center justify-center mb-6 group-hover:bg-green-600 transition-colors">
                  <FileText className="w-8 h-8 text-green-600 group-hover:text-white transition-colors" />
                </div>
                <h3 className="text-2xl font-bold text-gray-900 mb-3 group-hover:text-green-700">
                  {t("service_labor_title")}
                </h3>
                <p className="text-gray-500 leading-relaxed">
                  {t("service_labor_desc")}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* UPLOAD VIEW */}
        {view === "upload" && (
          <div className="flex-1 flex flex-col items-center justify-center p-4">
            <div className="text-center mb-10">
              <h2 className="text-3xl font-bold text-gray-900 mb-4">
                {t(
                  selectedService === "labor"
                    ? "upload_title_labor"
                    : "upload_title"
                )}
              </h2>
              <p className="text-gray-500">
                {t(
                  selectedService === "labor"
                    ? "upload_desc_labor"
                    : "upload_desc"
                )}
              </p>
            </div>

            <div className="flex gap-6 max-w-4xl w-full">
              {/* Contract Upload */}
              <div
                className={`flex-1 border-2 border-dashed rounded-2xl p-8 flex flex-col items-center justify-center transition-all cursor-pointer hover:border-indigo-400 group h-80 ${
                  contractFile
                    ? "border-indigo-500 bg-indigo-50"
                    : "border-gray-300 bg-white"
                }`}
              >
                <input
                  type="file"
                  className="hidden"
                  id="contract-upload"
                  accept=".pdf,.jpg,.png"
                  onChange={(e) => setContractFile(e.target.files?.[0] || null)}
                />
                <label
                  htmlFor="contract-upload"
                  className="flex flex-col items-center w-full h-full justify-center cursor-pointer"
                >
                  <div
                    className={`p-4 rounded-full mb-4 transition-colors ${
                      contractFile
                        ? "bg-white text-indigo-600 shadow-md"
                        : "bg-gray-100 text-gray-400 group-hover:bg-indigo-50 group-hover:text-indigo-500"
                    }`}
                  >
                    <FileText className="w-8 h-8" />
                  </div>
                  <h3 className="font-bold text-lg text-gray-800 mb-1 flex flex-col items-center">
                    <span>
                      {selectedService === "labor"
                        ? translations.ko.contract_label_labor
                        : translations.ko.contract_label}
                    </span>
                    {currentLang !== "ko" && (
                      <span className="text-sm text-gray-500 font-normal mt-0.5">
                        {t(
                          selectedService === "labor"
                            ? "contract_label_labor"
                            : "contract_label"
                        )}
                      </span>
                    )}
                  </h3>
                  <div className="text-sm text-gray-400 mb-4 flex flex-col items-center">
                    {contractFile ? (
                      contractFile.name
                    ) : (
                      <>
                        <span>{translations.ko.click_to_select}</span>
                        {currentLang !== "ko" && (
                          <span className="text-xs text-gray-300 mt-0.5">
                            {t("click_to_select")}
                          </span>
                        )}
                      </>
                    )}
                  </div>
                  {contractFile && (
                    <div className="text-xs bg-indigo-200 text-indigo-800 px-3 py-1 rounded-full font-bold">
                      {t("upload_done")}
                    </div>
                  )}
                </label>
              </div>

              {/* Registry Upload (Conditionally Rendered) */}
              {selectedService === "rent" && (
                <div
                  className={`flex-1 border-2 border-dashed rounded-2xl p-8 flex flex-col items-center justify-center transition-all cursor-pointer hover:border-blue-400 group h-80 ${
                    registryFile
                      ? "border-blue-500 bg-blue-50"
                      : "border-gray-300 bg-white"
                  }`}
                >
                  <input
                    type="file"
                    className="hidden"
                    id="registry-upload"
                    accept=".pdf,.jpg,.png"
                    onChange={(e) =>
                      setRegistryFile(e.target.files?.[0] || null)
                    }
                  />
                  <label
                    htmlFor="registry-upload"
                    className="flex flex-col items-center w-full h-full justify-center cursor-pointer"
                  >
                    <div
                      className={`p-4 rounded-full mb-4 transition-colors ${
                        registryFile
                          ? "bg-white text-blue-600 shadow-md"
                          : "bg-gray-100 text-gray-400 group-hover:bg-blue-50 group-hover:text-blue-500"
                      }`}
                    >
                      <Scan className="w-8 h-8" />
                    </div>
                    <h3 className="font-bold text-lg text-gray-800 mb-1 flex flex-col items-center">
                      <span>{translations.ko.registry_label}</span>
                      {currentLang !== "ko" && (
                        <span className="text-sm text-gray-500 font-normal mt-0.5">
                          {t("registry_label")}
                        </span>
                      )}
                    </h3>
                    <div className="text-sm text-gray-400 mb-4 flex flex-col items-center">
                      {registryFile ? (
                        registryFile.name
                      ) : (
                        <>
                          <span>{translations.ko.click_to_select}</span>
                          {currentLang !== "ko" && (
                            <span className="text-xs text-gray-300 mt-0.5">
                              {t("click_to_select")}
                            </span>
                          )}
                        </>
                      )}
                    </div>
                    {registryFile && (
                      <div className="text-xs bg-blue-200 text-blue-800 px-3 py-1 rounded-full font-bold">
                        {t("upload_done")}
                      </div>
                    )}
                  </label>
                </div>
              )}
            </div>

            <div className="mt-10 w-full max-w-md">
              {error && (
                <div className="mb-4 p-4 bg-red-50 text-red-600 rounded-lg text-sm text-center border border-red-100">
                  {error.message}
                </div>
              )}
              <button
                onClick={handleAnalyze}
                disabled={
                  selectedService === "rent"
                    ? !contractFile || !registryFile
                    : !contractFile
                }
                className="w-full py-4 bg-gray-900 hover:bg-black text-white text-lg font-bold rounded-xl shadow-xl transition-all disabled:opacity-30 disabled:cursor-not-allowed transform active:scale-95"
              >
                {t("analyze_btn")}
              </button>
              <div className="mt-8 p-5 bg-gray-50 rounded-2xl border border-gray-100 text-left space-y-3">
                <div className="flex gap-3 items-start">
                  <ShieldCheck className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
                  <p className="text-xs text-gray-500 leading-relaxed">
                    {t("notice_pii")}
                  </p>
                </div>
                <div className="flex gap-3 items-start">
                  <AlertTriangle className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
                  <p className="text-xs text-gray-500 leading-relaxed">
                    {t("notice_legal")}
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ANALYZING VIEW (Animation) */}
        {view === "analyzing" && (
          <div className="flex-1 flex flex-col items-center justify-center bg-white">
            {error ? (
              <div className="max-w-md w-full p-8 text-center animate-in fade-in zoom-in duration-300">
                <div className="w-20 h-20 bg-red-50 rounded-full flex items-center justify-center mx-auto mb-6 border border-red-100">
                  <AlertTriangle className="w-10 h-10 text-red-500" />
                </div>
                <h3 className="text-2xl font-bold text-gray-900 mb-3">
                  분석 중 오류가 발생했습니다
                </h3>
                <p className="text-gray-500 mb-6">
                  문서 처리 중 문제가 발생했습니다. 다시 시도해주세요.
                </p>
                <div className="p-4 bg-red-50 border border-red-100 text-red-700 rounded-xl mb-8 text-sm break-keep leading-relaxed shadow-sm">
                  {error.message}
                </div>
                <button
                  onClick={() => setView("upload")}
                  className="w-full py-4 bg-gray-900 text-white rounded-xl font-bold hover:bg-black transition-all shadow-lg hover:shadow-xl transform hover:-translate-y-0.5"
                >
                  다시 시도하기
                </button>
              </div>
            ) : (
              <>
                <div className="relative mb-12">
                  {/* Scanning Animation */}
                  <div className="w-32 h-44 bg-gray-50 border-2 border-gray-200 rounded-lg shadow-inner relative overflow-hidden flex flex-col p-3 space-y-3">
                    <div className="h-2 bg-gray-200 rounded w-3/4"></div>
                    <div className="h-2 bg-gray-200 rounded w-full"></div>
                    <div className="h-2 bg-gray-200 rounded w-5/6"></div>
                    <div className="h-2 bg-gray-200 rounded w-full"></div>
                    <div className="h-2 bg-gray-200 rounded w-4/5"></div>

                    {/* Scan Beam */}
                    <div className="absolute top-0 left-0 w-full h-1 bg-indigo-500/50 shadow-[0_0_10px_rgba(99,102,241,0.5)] animate-[scan_2s_ease-in-out_infinite]"></div>
                  </div>
                </div>

                <h2 className="text-3xl font-bold text-gray-900 mb-3">
                  {t("analyzing")}
                </h2>
                <p className="text-lg text-gray-500 mb-12">
                  {t("analyzing_time_msg")}
                </p>

                {/* Progress Checklist */}
                <div className="space-y-6 w-full max-w-md transition-all">
                  <ProgressItem
                    step={1}
                    current={progressStep}
                    label={t("prog_ocr")}
                    icon={Scan}
                  />
                  <ProgressItem
                    step={2}
                    current={progressStep}
                    label={t("prog_legal")}
                    icon={AlertTriangle}
                  />
                  <ProgressItem
                    step={3}
                    current={progressStep}
                    label={t("prog_pii")}
                    icon={ShieldCheck}
                  />
                  <ProgressItem
                    step={4}
                    current={progressStep}
                    label={t("prog_ai")}
                    icon={Brain}
                  />
                </div>

                <button
                  onClick={handleStopAnalysis}
                  className="mt-12 px-6 py-3 bg-white border border-gray-300 rounded-full text-gray-500 font-medium hover:bg-gray-50 hover:text-red-500 hover:border-red-200 transition-all shadow-sm flex items-center gap-2"
                >
                  <LogOut className="w-4 h-4 rotate-180" />
                  {t("stop_analysis")}
                </button>
                <div className="h-10"></div>
              </>
            )}
          </div>
        )}

        {/* PROFILE VIEW */}
        {view === "profile" && (
          <div className="flex-1 flex flex-col items-center p-8 overflow-y-auto">
            <div className="max-w-4xl w-full">
              {/* Profile Wrapper */}
              <div className="bg-white rounded-3xl p-8 shadow-xl border border-gray-100 mb-8">
                <div className="flex items-center gap-6 mb-8 border-b border-gray-100 pb-8">
                  <div className="w-24 h-24 bg-indigo-50 rounded-full flex items-center justify-center border-4 border-indigo-100">
                    <UserIcon className="w-10 h-10 text-indigo-600" />
                  </div>
                  <div>
                    <h2 className="text-3xl font-bold text-gray-900 mb-1">
                      {user?.name}
                    </h2>
                    <p className="text-gray-500">{user?.email}</p>
                  </div>
                </div>

                {/* History Section in Profile */}
                <h3 className="text-xl font-bold text-gray-800 mb-4 flex items-center gap-2">
                  <Clock className="w-5 h-5 text-gray-500" />
                  {t("profile_history_title")}
                </h3>

                <div className="grid gap-4 mb-12">
                  {historyList.length === 0 ? (
                    <div className="text-center py-12 bg-gray-50 rounded-2xl border border-dashed border-gray-200">
                      <p className="text-gray-400">{t("no_history_msg")}</p>
                      <button
                        onClick={goHome}
                        className="mt-4 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-bold hover:bg-indigo-700 transition"
                      >
                        {t("start_analysis_btn")}
                      </button>
                    </div>
                  ) : (
                    historyList.map((item) => {
                      const dateStr = item.created_at;
                      // No complex timezone math needed if display only, but sticking to existing logic is safer
                      // Let's use the code from original history view for consistency

                      const originalTitle =
                        item.result_json?.summary?.title || "문서 분석";
                      // Truncate UUID if title is just ID
                      const formattedTitle =
                        originalTitle.length > 20
                          ? "..." + originalTitle.slice(-8)
                          : originalTitle;

                      const langCode =
                        item.result_json?.summary?.language || "ko";
                      const langMap: Record<string, string> = {
                        ko: "KR",
                        en: "EN",
                        ne: "NP",
                        km: "KH",
                        id: "ID",
                        vi: "VN",
                        my: "MM",
                        th: "TH",
                      };
                      const langLabel =
                        langMap[langCode] || langCode.toUpperCase();

                      const isLease = item.result_json?.documents?.registry_url;
                      // Note: We don't have 't' function context for "contract_label" easily inside map unless we use t

                      const contractType = isLease
                        ? "임대차 계약"
                        : "근로 계약"; // Hardcoded or use translations if available
                      // Let's reuse t() it is available in scope

                      const contractTypeLabel = isLease
                        ? t("contract_label")
                        : t("contract_label_labor");

                      return (
                        <div
                          key={item.id}
                          onClick={() => {
                            setResult(item.result_json);
                            setView("result");
                          }}
                          className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm hover:shadow-md hover:border-indigo-300 cursor-pointer transition-all flex justify-between items-center"
                        >
                          <div>
                            <div className="flex items-center gap-2 mb-1">
                              <span
                                className={`px-2 py-0.5 rounded text-xs font-bold ${
                                  isLease
                                    ? "bg-blue-100 text-blue-700"
                                    : "bg-green-100 text-green-700"
                                }`}
                              >
                                {contractTypeLabel}
                              </span>
                              <span className="px-2 py-0.5 rounded text-xs font-bold bg-gray-100 text-gray-600 border border-gray-200">
                                {langLabel}
                              </span>
                              <span className="text-gray-400 text-xs">
                                {(() => {
                                  if (!item.created_at) return "";
                                  let dateStr = item.created_at;
                                  if (
                                    !dateStr.endsWith("Z") &&
                                    !dateStr.includes("+")
                                  ) {
                                    dateStr += "Z";
                                  }
                                  const dateObj = new Date(dateStr);
                                  const formatter = new Intl.DateTimeFormat(
                                    "en-US",
                                    {
                                      timeZone: "Asia/Seoul",
                                      year: "numeric",
                                      month: "2-digit",
                                      day: "2-digit",
                                      hour: "2-digit",
                                      minute: "2-digit",
                                      hour12: false,
                                    }
                                  );
                                  const parts =
                                    formatter.formatToParts(dateObj);
                                  const getPart = (type: string) =>
                                    parts.find((p) => p.type === type)?.value;
                                  return `${getPart("year")}. ${getPart(
                                    "month"
                                  )}. ${getPart("day")}. ${getPart(
                                    "hour"
                                  )}:${getPart("minute")}`;
                                })()}
                              </span>
                            </div>
                            <div className="font-bold text-lg text-gray-800">
                              {t("result_title")}
                            </div>
                          </div>
                          <div className="flex flex-col items-end gap-2">
                            <div className="flex flex-col items-end">
                              <span className="text-red-500 font-bold text-xl">
                                {item.result_json?.summary?.risk_count || 0}
                              </span>
                              <span className="text-xs text-red-400">
                                {t("risk_found")}
                              </span>
                            </div>
                            <button
                              onClick={(e) => handleDeleteHistory(e, item.id)}
                              className="flex items-center gap-1 text-xs text-gray-400 hover:text-red-500 transition-colors bg-gray-50 hover:bg-red-50 px-2 py-1 rounded"
                            >
                              <Trash2 className="w-3 h-3" />
                              {t("delete")}
                            </button>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>

                {/* Delete Account Section */}
                <div className="border-t border-gray-100 pt-8 mt-12">
                  <h3 className="text-lg font-bold text-gray-900 mb-2">
                    {t("delete_account_title")}
                  </h3>
                  <p className="text-sm text-gray-500 mb-4">
                    {t("delete_account_desc")}
                  </p>
                  <button
                    onClick={handleDeleteAccount}
                    className="flex items-center gap-2 px-5 py-3 bg-red-50 text-red-600 rounded-xl hover:bg-red-100 font-bold transition-colors border border-red-100"
                  >
                    <Trash2 className="w-4 h-4" />
                    {t("delete_account_btn")}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* HISTORY VIEW */}
        {view === "history" && (
          <div className="flex-1 flex flex-col items-center p-8 overflow-y-auto">
            <div className="max-w-4xl w-full">
              <h2 className="text-3xl font-bold text-gray-900 mb-8 flex items-center gap-3">
                <Clock className="w-8 h-8 text-indigo-600" />
                {t("history_title")}
              </h2>

              <div className="grid gap-4">
                {historyList.map((item) => {
                  // Fix: Backend returns naive UTC string (e.g. "2023-12-26T02:27:00")
                  // Browser interprets this as Local Time. We must force it to be UTC by appending 'Z' if missing.
                  let dateStr = item.created_at;
                  if (!dateStr.endsWith("Z") && !dateStr.includes("+")) {
                    dateStr += "Z";
                  }
                  const dateObj = new Date(dateStr);

                  // Manually construct KST string: YYYY-MM-DD HH:mm
                  // Using Intl to get parts in KST
                  const formatter = new Intl.DateTimeFormat("en-US", {
                    timeZone: "Asia/Seoul",
                    year: "numeric",
                    month: "2-digit",
                    day: "2-digit",
                    hour: "2-digit",
                    minute: "2-digit",
                    hour12: false,
                  });

                  const parts = formatter.formatToParts(dateObj);
                  const getPart = (type: string) =>
                    parts.find((p) => p.type === type)?.value;

                  const y = getPart("year");
                  const m = getPart("month");
                  const d = getPart("day");
                  const h = getPart("hour"); // 0-23
                  const mi = getPart("minute");

                  const formattedTitle = `${y}-${m}-${d} ${h}:${mi}`;

                  // Language Display Map
                  const langMap: Record<string, string> = {
                    ko: "KR",
                    en: "EN",
                    ne: "NP",
                    km: "KH",
                    id: "ID",
                    vi: "VN",
                    my: "MM",
                    th: "TH",
                  };
                  const langCode = item.result_json?.summary?.language || "ko";
                  const langLabel = langMap[langCode] || langCode.toUpperCase();

                  // Contract Type Translation
                  const isLease = item.result_json?.documents?.registry_url;
                  const contractType = isLease
                    ? t("contract_label")
                    : t("contract_label_labor");

                  return (
                    <div
                      key={item.id}
                      onClick={() => {
                        setLanguage(
                          item.result_json?.summary?.language || "ko"
                        );
                        setResult(item.result_json);
                        setViewerTab("contract");
                        setView("result");
                      }}
                      className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm hover:shadow-md hover:border-indigo-300 cursor-pointer transition-all flex justify-between items-center"
                    >
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <span
                            className={`px-2 py-0.5 rounded text-xs font-bold ${
                              isLease
                                ? "bg-blue-100 text-blue-700"
                                : "bg-green-100 text-green-700"
                            }`}
                          >
                            {contractType}
                          </span>
                          <span className="px-2 py-0.5 rounded text-xs font-bold bg-gray-100 text-gray-600 border border-gray-200">
                            {langLabel}
                          </span>
                          <span className="text-gray-400 text-xs">
                            {formattedTitle}
                          </span>
                        </div>
                        <div className="font-bold text-lg text-gray-800">
                          {t("result_title")} ({formattedTitle})
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-2">
                        <div className="flex flex-col items-end">
                          <span className="text-red-500 font-bold text-xl">
                            {item.result_json?.summary?.risk_count || 0}
                          </span>
                          <span className="text-xs text-red-400">
                            {t("risk_found")}
                          </span>
                        </div>
                        <button
                          onClick={(e) => handleDeleteHistory(e, item.id)}
                          className="flex items-center gap-1 text-xs text-gray-400 hover:text-red-500 transition-colors bg-gray-50 hover:bg-red-50 px-2 py-1 rounded"
                        >
                          <Trash2 className="w-3 h-3" />
                          {t("delete")}
                        </button>
                      </div>
                    </div>
                  );
                })}
                {historyList.length === 0 && (
                  <div className="text-center text-gray-400 py-12">
                    히스토리가 없습니다.
                  </div>
                )}
              </div>

              <button
                onClick={() => setView("service_select")}
                className="mt-8 text-gray-500 hover:text-gray-900 underline"
              >
                돌아가기
              </button>
            </div>
          </div>
        )}

        {/* RESULT VIEW */}
        {view === "result" && result && (
          <div className="flex-1 flex overflow-hidden">
            {/* Left Panel: Report */}
            <div className="w-5/12 min-w-[400px] bg-white border-r border-gray-200 flex flex-col overflow-y-auto">
              <div className="p-8">
                {(() => {
                  // Helper for report-specific translation
                  const rLang = (result.summary?.language ||
                    currentLang) as LanguageCode;
                  const tr = (key: keyof typeof translations.ko) => {
                    return (
                      translations[rLang]?.[key] ||
                      translations["ko"][key] ||
                      key
                    );
                  };

                  return (
                    <>
                      <div className="flex justify-between items-center mb-8">
                        <h2 className="text-2xl font-bold text-gray-900">
                          {tr("result_title")}
                        </h2>
                        <button
                          onClick={() => setView("upload")}
                          className="text-sm font-medium text-gray-500 hover:text-indigo-600 underline"
                        >
                          {t("restart_btn")}
                        </button>
                      </div>

                      {/* Summary Badges */}
                      <div className="flex gap-2 mb-6">
                        <div className="flex-1 bg-red-50 p-4 rounded-xl border border-red-100 flex flex-col items-center justify-center text-center">
                          <span className="text-red-500 font-bold text-2xl mb-1">
                            {result.summary.risk_count}
                          </span>
                          <span className="text-xs text-red-600 font-bold">
                            {tr("risk_found")}
                          </span>
                        </div>
                        {/* Safe Items Removed as per request */}
                      </div>

                      <div className="mb-8 p-4 bg-yellow-50 border border-yellow-200 rounded-xl flex gap-3 items-start">
                        <AlertTriangle className="w-5 h-5 text-yellow-600 flex-shrink-0 mt-0.5" />
                        <div>
                          <h4 className="font-bold text-yellow-800 text-sm mb-1">
                            {tr("risk_alert_title")}
                          </h4>
                          <p className="text-xs text-yellow-700 leading-relaxed">
                            {tr("risk_alert_msg_1")} {result.summary.risk_count}
                            {tr(
                              selectedService === "labor"
                                ? "risk_alert_msg_2_labor"
                                : "risk_alert_msg_2"
                            )}
                          </p>
                        </div>
                      </div>

                      {/* Details List (Only Failures) */}
                      <div className="space-y-6">
                        {result.rules
                          .filter((r: any) => r.status === "FAIL")
                          .map((rule: any, idx: number) => (
                            <div
                              key={idx}
                              className={`p-6 rounded-xl border bg-white shadow-sm transition-all ${
                                rule.severity === "HIGH"
                                  ? "border-red-200 ring-1 ring-red-50"
                                  : "border-orange-200 ring-1 ring-orange-50"
                              }`}
                            >
                              <div className="flex justify-between items-start mb-4">
                                <div className="flex items-center gap-3">
                                  <span
                                    className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold shadow-sm ${
                                      rule.severity === "HIGH"
                                        ? "bg-red-100 text-red-600"
                                        : "bg-orange-100 text-orange-600"
                                    }`}
                                  >
                                    {idx + 1}
                                  </span>
                                  <h3 className="font-bold text-gray-900 text-lg">
                                    {rule.title}
                                  </h3>
                                </div>
                                <span
                                  className={`text-xs px-2.5 py-1 rounded-full font-bold ${
                                    rule.severity === "HIGH"
                                      ? "bg-red-100 text-red-600"
                                      : "bg-orange-100 text-orange-600"
                                  }`}
                                >
                                  {rule.severity === "HIGH"
                                    ? tr("danger")
                                    : tr("caution")}
                                </span>
                              </div>

                              {/* Quote Evidence */}
                              <div className="mb-5 p-4 bg-gray-50 rounded-lg border border-gray-100 font-serif text-gray-700 italic relative">
                                <span className="absolute top-2 left-2 text-3xl text-gray-200 pointer-events-none">
                                  "
                                </span>
                                <p className="pl-4 relative z-10 whitespace-pre-wrap">
                                  {rule.evidence.detail}
                                </p>
                              </div>

                              {/* AI Advice Sections */}
                              <div className="space-y-4">
                                {/* Legal Review */}
                                <div>
                                  <h4 className="text-sm font-bold text-gray-900 mb-1 flex items-center gap-1.5">
                                    <span className="text-lg">⚖️</span>{" "}
                                    {tr("legal_review")}
                                  </h4>
                                  <p className="text-sm text-gray-600 leading-relaxed pl-1 border-l-2 border-gray-200 ml-1">
                                    {rule.ai_advice?.legal_review ||
                                      tr("ai_error_msg")}
                                  </p>
                                </div>

                                {/* Action Guide */}
                                <div>
                                  <h4 className="text-sm font-bold text-indigo-900 mb-1 flex items-center gap-1.5">
                                    <span className="text-lg">💡</span>{" "}
                                    {tr("action_guide")}
                                  </h4>
                                  <div className="text-sm text-indigo-700 bg-indigo-50 p-3 rounded-lg leading-relaxed">
                                    {rule.ai_advice?.action_guide ||
                                      tr("consult_expert_msg")}
                                  </div>
                                </div>
                              </div>
                            </div>
                          ))}

                        {result.rules.filter((r: any) => r.status === "FAIL")
                          .length === 0 && (
                          <div className="p-8 text-center bg-green-50 rounded-xl border border-green-100">
                            <p className="text-green-700 font-bold text-lg mb-2">
                              🎉 {tr("safe_title")}
                            </p>
                            <p className="text-green-600 text-sm">
                              {tr("safe_desc")}
                            </p>
                          </div>
                        )}
                      </div>

                      {/* AI Advice */}
                      <div className="mt-8 pt-8 border-t border-gray-100">
                        <h3 className="flex items-center gap-2 font-bold text-indigo-900 mb-4">
                          <Brain className="w-5 h-5 text-indigo-600" />{" "}
                          {tr("ai_summary_title")}
                        </h3>
                        <div className="bg-indigo-50/80 p-5 rounded-xl border border-indigo-100 text-sm text-indigo-900 leading-7">
                          {result.summary_text ? (
                            result.summary_text
                              .split("\n")
                              .map((line: any, i: number) => {
                                const trimmed = line.trim();

                                // Handle Headers ###
                                if (trimmed.startsWith("###")) {
                                  return (
                                    <h4
                                      key={i}
                                      className="text-sm font-bold text-indigo-800 mt-4 mb-2"
                                    >
                                      {trimmed
                                        .replace(/^###\s*/, "")
                                        .replace(/\*\*/g, "")}
                                    </h4>
                                  );
                                }

                                // Handle List Items (- )
                                if (trimmed.startsWith("- ")) {
                                  const content = line.replace(/^\s*-\s*/, "");
                                  return (
                                    <div
                                      key={i}
                                      className="flex items-start gap-2 mb-1 pl-1"
                                    >
                                      <span className="text-indigo-400 font-bold mt-0.5">
                                        •
                                      </span>
                                      <p className="text-indigo-900 leading-relaxed">
                                        {content
                                          .split(/(\*\*.*?\*\*)/g)
                                          .map((part: string, j: number) =>
                                            part.startsWith("**") ? (
                                              <span
                                                key={j}
                                                className="font-bold bg-indigo-100 px-1 rounded"
                                              >
                                                {part.slice(2, -2)}
                                              </span>
                                            ) : (
                                              part
                                            )
                                          )}
                                      </p>
                                    </div>
                                  );
                                }

                                // Handle Standard Text
                                if (!trimmed)
                                  return <div key={i} className="h-2"></div>;

                                return (
                                  <p key={i} className="mb-2 last:mb-0">
                                    {line
                                      .split(/(\*\*.*?\*\*)/g)
                                      .map((part: string, j: number) =>
                                        part.startsWith("**") ? (
                                          <span
                                            key={j}
                                            className="font-bold bg-indigo-100 px-1 rounded"
                                          >
                                            {part.slice(2, -2)}
                                          </span>
                                        ) : (
                                          part
                                        )
                                      )}
                                  </p>
                                );
                              })
                          ) : (
                            <p className="text-gray-400 italic">
                              AI 의견 생성 중...
                            </p>
                          )}
                        </div>
                      </div>

                      {/* Disclaimers */}
                      <div className="mt-8 p-5 bg-gray-50 rounded-2xl border border-gray-100 text-left space-y-3">
                        <div className="flex gap-3 items-start">
                          <ShieldCheck className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
                          <p className="text-xs text-gray-500 leading-relaxed">
                            {tr("notice_pii")}
                          </p>
                        </div>
                        <div className="flex gap-3 items-start">
                          <AlertTriangle className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
                          <p className="text-xs text-gray-500 leading-relaxed">
                            {tr("notice_legal")}
                          </p>
                        </div>
                      </div>
                    </>
                  );
                })()}
              </div>
            </div>

            {/* Right Panel: Viewer */}
            <div className="flex-1 bg-gray-100 relative flex flex-col">
              <div className="absolute top-6 left-1/2 transform -translate-x-1/2 z-10 flex bg-white rounded-full shadow-lg p-1 border border-gray-200">
                <button
                  onClick={() => setViewerTab("contract")}
                  className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-bold transition-all ${
                    viewerTab === "contract"
                      ? "bg-gray-900 text-white shadow-md scale-105"
                      : "text-gray-500 hover:bg-gray-100"
                  }`}
                >
                  <FileText className="w-4 h-4" />{" "}
                  {t(
                    selectedService === "labor"
                      ? "contract_label_labor"
                      : "contract_label"
                  )}
                </button>
                {selectedService === "rent" && (
                  <button
                    onClick={() => setViewerTab("registry")}
                    className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-bold transition-all ${
                      viewerTab === "registry"
                        ? "bg-gray-900 text-white shadow-md scale-105"
                        : "text-gray-500 hover:bg-gray-100"
                    }`}
                  >
                    <Scan className="w-4 h-4" /> {t("registry_label")}
                  </button>
                )}
              </div>

              <div className="flex-1 p-8 pt-24 overflow-auto flex justify-center">
                <div className="relative w-full h-full shadow-2xl rounded-xl overflow-hidden bg-white border border-gray-200">
                  <iframe
                    src={
                      viewerTab === "contract"
                        ? result.documents.masked_pdf_url
                        : result.documents.registry_url
                    }
                    className="w-full h-full"
                  />
                </div>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Global CSS for scanning animation */}
      <style jsx global>{`
        @keyframes scan {
          0% {
            top: 0;
            opacity: 0;
          }
          10% {
            opacity: 1;
          }
          90% {
            opacity: 1;
          }
          100% {
            top: 100%;
            opacity: 0;
          }
        }
      `}</style>
      <SignupModal
        isOpen={isSignupOpen}
        onClose={() => setIsSignupOpen(false)}
        lang={currentLang}
      />
    </div>
  );
}

// Component helper for Checklist
function ProgressItem({ step, current, label, icon: Icon }: any) {
  const status =
    current > step ? "done" : current === step ? "active" : "waiting";
  return (
    <div
      className={`flex items-center gap-4 transition-opacity duration-500 ${
        status === "waiting" ? "opacity-30" : "opacity-100"
      }`}
    >
      <div
        className={`w-8 h-8 rounded-full flex items-center justify-center border transition-all duration-500 ${
          status === "done"
            ? "bg-indigo-600 border-indigo-600 text-white"
            : status === "active"
            ? "bg-white border-indigo-600 text-indigo-600 animate-pulse"
            : "bg-gray-100 border-gray-300 text-gray-300"
        }`}
      >
        {status === "done" ? (
          <Check className="w-4 h-4" />
        ) : (
          <div className="w-2.5 h-2.5 rounded-full bg-current" />
        )}
      </div>
      <div
        className={`flex items-center gap-3 ${
          status === "active" ? "text-indigo-900 font-bold" : "text-gray-600"
        }`}
      >
        <Icon className="w-5 h-5" />
        <span className="text-lg">{label}</span>
        {status === "active" && (
          <span className="text-xs text-indigo-500 animate-bounce">...</span>
        )}
      </div>
    </div>
  );
}

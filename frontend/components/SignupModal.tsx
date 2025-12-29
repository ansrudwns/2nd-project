import React, { useState, useEffect } from "react";
import axios from "axios";
import { X, Check, AlertCircle, CheckCircle2, Loader2 } from "lucide-react";

import TermsModal from "./TermsModal";

interface SignupModalProps {
  isOpen: boolean;
  onClose: () => void;
  lang: string;
}

export default function SignupModal({
  isOpen,
  onClose,
  lang,
}: SignupModalProps) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  // Validation States
  const [emailError, setEmailError] = useState("");
  const [isEmailChecked, setIsEmailChecked] = useState(false);
  const [isCheckingEmail, setIsCheckingEmail] = useState(false);
  const [confirmPasswordError, setConfirmPasswordError] = useState("");
  const [isSigningUp, setIsSigningUp] = useState(false);

  // Password Rules States
  const [pwdValid, setPwdValid] = useState({
    length: false,
    letter: false,
    number: false,
    special: false,
  });

  // Terms States
  const [showTermsModal, setShowTermsModal] = useState(false);
  const [terms, setTerms] = useState({
    privacy: false,
    legal: false,
    prevention: false,
  });

  // Reset state when modal opens
  useEffect(() => {
    if (isOpen) {
      setName("");
      setEmail("");
      setPassword("");
      setConfirmPassword("");
      setEmailError("");
      setIsEmailChecked(false);
      setIsCheckingEmail(false);
      setConfirmPasswordError("");
      setPwdValid({
        length: false,
        letter: false,
        number: false,
        special: false,
      });
      setShowTermsModal(false);
      setTerms({
        privacy: false,
        legal: false,
        prevention: false,
      });
    }
  }, [isOpen]);

  useEffect(() => {
    // Real-time Password Validation
    setPwdValid({
      length: password.length >= 8,
      letter: /[A-Za-z]/.test(password),
      number: /\d/.test(password),
      special: /[@$!%*#?&]/.test(password),
    });

    // Check match real-time
    if (confirmPassword && password !== confirmPassword) {
      setConfirmPasswordError("비밀번호가 일치하지 않습니다.");
    } else {
      setConfirmPasswordError("");
    }
  }, [password, confirmPassword]);

  if (!isOpen) return null;

  // Regex for final check (same as individual rules combined)
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  const handleCheckEmail = async () => {
    if (!emailRegex.test(email)) {
      setEmailError("유효한 이메일 형식이 아닙니다.");
      // Add alert so user knows button was clicked
      alert("올바른 이메일 형식을 입력해주세요.");
      return;
    }
    setIsCheckingEmail(true);
    try {
      const response = await axios.post(
        `${
          process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
        }/api/v1/auth/check-email`,
        { email }
      );
      if (response.data.exists) {
        setEmailError("이미 사용 중인 이메일입니다.");
        setIsEmailChecked(false);
      } else {
        setEmailError("");
        setIsEmailChecked(true);
        // alert removed for smoother UX, relying on green text
      }
    } catch (error) {
      console.error(error);
      setEmailError("이메일 확인 중 오류가 발생했습니다.");
    } finally {
      setIsCheckingEmail(false);
    }
  };

  const handleSignup = async () => {
    let isValid = true;

    if (!name.trim()) {
      alert("이름을 입력해주세요.");
      return;
    }

    if (!isEmailChecked) {
      setEmailError("이메일 중복 확인을 해주세요.");
      isValid = false;
    }

    // Check all password rules
    if (!Object.values(pwdValid).every(Boolean)) {
      isValid = false; // Checklist will show what's missing
    }

    if (password !== confirmPassword) {
      setConfirmPasswordError("비밀번호가 일치하지 않습니다.");
      isValid = false;
    }

    if (!terms.privacy || !terms.legal || !terms.prevention) {
      alert("모든 약관에 동의해야 합니다.");
      return;
    }

    if (!isValid) return;

    setIsSigningUp(true);
    try {
      // Artificial delay for UX (1.5s)
      await new Promise((resolve) => setTimeout(resolve, 1500));

      await axios.post(
        `${
          process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
        }/api/v1/auth/signup`,
        {
          full_name: name,
          email,
          password,
        }
      );
      alert("회원가입이 완료되었습니다!");
      onClose();
    } catch (error: any) {
      console.error(error);
      const errorMessage =
        error.response?.data?.detail || error.message || "회원가입 실패";
      alert(`오류가 발생했습니다: ${errorMessage}`);
    } finally {
      setIsSigningUp(false);
    }
  };

  const PasswordRequirement = ({
    met,
    text,
  }: {
    met: boolean;
    text: string;
  }) => (
    <div
      className={`flex items-center text-xs space-x-1 ${
        met ? "text-green-600 font-medium" : "text-gray-400"
      }`}
    >
      {met ? (
        <CheckCircle2 className="w-3 h-3" />
      ) : (
        <div className="w-3 h-3 rounded-full border border-gray-300" />
      )}
      <span>{text}</span>
    </div>
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="bg-white rounded-3xl w-full max-w-md p-8 relative shadow-2xl animate-in fade-in zoom-in duration-200">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 transition-colors"
        >
          <X className="w-6 h-6" />
        </button>

        <h2 className="text-2xl font-bold mb-6 text-center text-gray-800 font-[family-name:var(--font-outfit)]">
          회원가입
        </h2>

        <div className="space-y-5">
          {/* Name Field */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              이름
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-4 py-3 rounded-xl border border-gray-200 bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-all"
              placeholder="이름을 입력하세요"
            />
          </div>

          {/* Email Field */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              이메일 (ID)
            </label>
            <div className="flex gap-2">
              <input
                type="email"
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  setIsEmailChecked(false);
                  if (
                    !emailRegex.test(e.target.value) &&
                    e.target.value.length > 0
                  ) {
                    setEmailError("이메일 형식이 올바르지 않습니다.");
                  } else {
                    setEmailError("");
                  }
                }}
                className={`flex-1 px-4 py-3 rounded-xl border ${
                  emailError
                    ? "border-red-500 bg-red-50 focus:ring-red-200"
                    : isEmailChecked
                    ? "border-green-500 bg-green-50 focus:ring-green-200"
                    : "border-gray-200 bg-gray-50 focus:ring-indigo-500"
                } focus:outline-none focus:ring-2 transition-all`}
                placeholder="user@example.com"
              />
              <button
                type="button"
                onClick={handleCheckEmail}
                disabled={isCheckingEmail || isEmailChecked}
                className={`px-4 py-2 rounded-xl text-sm font-bold transition-all whitespace-nowrap flex items-center justify-center min-w-[80px] ${
                  isEmailChecked
                    ? "bg-green-100 text-green-700 border border-green-200"
                    : "bg-gray-800 text-white hover:bg-gray-900 shadow-md disabled:opacity-70"
                }`}
              >
                {isCheckingEmail ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : isEmailChecked ? (
                  <Check className="w-5 h-5 mx-auto" />
                ) : (
                  "중복확인"
                )}
              </button>
            </div>
            {emailError && (
              <p className="text-red-500 text-xs mt-1.5 ml-1 flex items-center animate-pulse">
                <AlertCircle className="w-3 h-3 mr-1" />
                {emailError}
              </p>
            )}
            {isEmailChecked && !emailError && (
              <p className="text-green-600 text-xs mt-1.5 ml-1 flex items-center font-medium">
                <CheckCircle2 className="w-3 h-3 mr-1" />
                사용 가능한 이메일입니다.
              </p>
            )}
          </div>

          {/* Password Field */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              비밀번호
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-4 py-3 rounded-xl border border-gray-200 bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-all mb-2"
              placeholder="비밀번호 입력"
            />
            {/* Real-time Validation Checklist */}
            <div className="grid grid-cols-2 gap-2 pl-1">
              <PasswordRequirement met={pwdValid.length} text="8자 이상" />
              <PasswordRequirement met={pwdValid.letter} text="영문 포함" />
              <PasswordRequirement met={pwdValid.number} text="숫자 포함" />
              <PasswordRequirement
                met={pwdValid.special}
                text="특수문자 포함"
              />
            </div>
          </div>

          {/* Confirm Password Field */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              비밀번호 확인
            </label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className={`w-full px-4 py-3 rounded-xl border ${
                confirmPasswordError ||
                (confirmPassword && password !== confirmPassword)
                  ? "border-red-500 bg-red-50 focus:ring-red-200"
                  : confirmPassword && password === confirmPassword
                  ? "border-green-500 bg-green-50 focus:ring-green-200"
                  : "border-gray-200 bg-gray-50 focus:ring-indigo-500"
              } focus:outline-none focus:ring-2 transition-all`}
              placeholder="비밀번호 다시 입력"
            />
            {confirmPasswordError && (
              <p className="text-red-500 text-xs mt-1.5 ml-1 flex items-center">
                <AlertCircle className="w-3 h-3 mr-1" />
                {confirmPasswordError}
              </p>
            )}
          </div>

          {/* Terms Button */}
          <div
            onClick={() => {
              if (!terms.privacy || !terms.legal || !terms.prevention) {
                setShowTermsModal(true);
              }
            }}
            className={`p-4 rounded-xl border transition-all cursor-pointer flex items-center justify-between group ${
              terms.privacy && terms.legal && terms.prevention
                ? "bg-indigo-50 border-indigo-200"
                : "bg-white border-gray-200 hover:border-indigo-300"
            }`}
          >
            <div className="flex items-center gap-3">
              <div
                className={`w-10 h-10 rounded-full flex items-center justify-center transition-colors ${
                  terms.privacy && terms.legal && terms.prevention
                    ? "bg-indigo-100 text-indigo-600"
                    : "bg-gray-100 text-gray-400 group-hover:bg-gray-200"
                }`}
              >
                <CheckCircle2 className="w-5 h-5" />
              </div>
              <div className="text-left flex-1 min-w-0">
                <p
                  className={`font-bold text-sm truncate pr-2 ${
                    terms.privacy && terms.legal && terms.prevention
                      ? "text-indigo-900"
                      : "text-gray-900"
                  }`}
                >
                  필수 약관 및 동의서 작성
                </p>
              </div>
            </div>

            <div
              className={`text-xs font-bold px-4 py-2 rounded-full transition-colors whitespace-nowrap shrink-0 ${
                terms.privacy && terms.legal && terms.prevention
                  ? "bg-indigo-600 text-white"
                  : "bg-gray-100 text-gray-500 group-hover:bg-gray-200"
              }`}
            >
              {terms.privacy && terms.legal && terms.prevention
                ? "동의 완료"
                : "약관 보기"}
            </div>
          </div>

          {/* Terms Modal */}
          <TermsModal
            isOpen={showTermsModal}
            onClose={() => setShowTermsModal(false)}
            onConfirm={() => {
              setTerms({
                privacy: true,
                legal: true,
                prevention: true,
              });
              setShowTermsModal(false);
            }}
          />

          {/* Submit Button */}
          <button
            onClick={handleSignup}
            disabled={
              !name ||
              !isEmailChecked ||
              !Object.values(pwdValid).every(Boolean) ||
              password !== confirmPassword ||
              !Object.values(terms).every(Boolean) ||
              isSigningUp
            }
            className={`w-full font-bold py-3.5 rounded-xl shadow-lg transition-all active:scale-[0.98] mt-2 flex items-center justify-center gap-2 ${
              !name ||
              !isEmailChecked ||
              !Object.values(pwdValid).every(Boolean) ||
              password !== confirmPassword ||
              !Object.values(terms).every(Boolean) ||
              isSigningUp
                ? "bg-gray-300 text-gray-500 cursor-not-allowed shadow-none"
                : "bg-indigo-600 hover:bg-indigo-700 text-white shadow-indigo-200"
            }`}
          >
            {isSigningUp ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                <span>가입 처리 중...</span>
              </>
            ) : (
              "회원가입 완료"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

import React, { useState, useEffect } from "react";
import { X, Check, FileText, AlertTriangle, ShieldCheck } from "lucide-react";

interface TermsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
}

export default function TermsModal({
  isOpen,
  onClose,
  onConfirm,
}: TermsModalProps) {
  const [agreements, setAgreements] = useState({
    privacy: false, // ① 개인정보 수집·이용 동의
    limitations: false, // ② 서비스 한계 및 법적 책임
    prevention: false, // ③ 사전 예방 목적
  });

  // Reset state when modal opens
  useEffect(() => {
    if (isOpen) {
      // Optional: Reset checks every time? Or keep them?
      // User said "Check is maintained" in SignupModal, but inside this popup,
      // if they reopen it, maybe show them checked?
      // For now, let's assume if they open it, it's to agree.
      // But the state is managed here.
      // Actually, if we want to "maintain" state, we should probably accept props.
      // But for simplicity in this flow, let's manage internal state and just confirming "All Agreed" passes back up.
    }
  }, [isOpen]);

  const toggleAll = () => {
    const allChecked = Object.values(agreements).every(Boolean);
    setAgreements({
      privacy: !allChecked,
      limitations: !allChecked,
      prevention: !allChecked,
    });
  };

  const isAllChecked = Object.values(agreements).every(Boolean);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in duration-200">
      <div className="bg-white rounded-3xl w-full max-w-2xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden relative">
        {/* Header */}
        <div className="p-6 border-b border-gray-100 flex items-center justify-between bg-gray-50/50">
          <div>
            <h2 className="text-2xl font-bold text-gray-900 font-[family-name:var(--font-outfit)]">
              서비스 이용 약관 동의
            </h2>
            <p className="text-sm text-gray-500 mt-1">
              안전한 서비스 이용을 위해 아래 내용을 꼭 확인해주세요.
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 rounded-full transition-colors text-gray-400 hover:text-gray-600"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-8 custom-scrollbar">
          {/* Section 1: Privacy */}
          <section className="space-y-3">
            <div className="flex items-start gap-4">
              <div className="mt-1 p-2 bg-blue-50 text-blue-600 rounded-lg shrink-0">
                <FileText className="w-5 h-5" />
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-bold text-gray-900 flex items-center gap-2">
                  ① 개인정보 수집·이용 동의
                  <span className="px-2 py-0.5 bg-red-100 text-red-600 text-xs rounded-full font-bold">
                    필수
                  </span>
                </h3>

                <div className="mt-3 bg-gray-50 p-4 rounded-xl text-sm text-gray-600 leading-relaxed border border-gray-100">
                  <p className="font-bold text-gray-800 mb-2">
                    [개인정보 수집·이용에 대한 동의]
                  </p>
                  <p className="mb-2">
                    CheckMate는 서비스 제공을 위해 아래와 같은 개인정보를
                    수집·이용합니다.
                  </p>
                  <ul className="list-disc pl-5 mb-2 space-y-1">
                    <li>
                      수집 항목: 이메일 주소(또는 계정 식별을 위한 최소 정보)
                    </li>
                    <li>
                      수집 목적: 이용자 식별, 서비스 제공 및 서비스 품질 개선
                    </li>
                    <li>
                      보유 및 이용 기간: 회원 탈퇴 시까지 또는 관련 법령에 따른
                      보관 기간
                    </li>
                  </ul>
                  <p className="text-gray-500 text-xs">
                    이용자는 개인정보 수집·이용에 대한 동의를 거부할 수 있으나,
                    동의하지 않을 경우 서비스 이용이 제한될 수 있습니다.
                  </p>
                </div>

                <label className="flex items-center gap-2 mt-3 cursor-pointer group">
                  <div
                    onClick={() =>
                      setAgreements((prev) => ({
                        ...prev,
                        privacy: !prev.privacy,
                      }))
                    }
                    className={`w-5 h-5 rounded border flex items-center justify-center transition-all ${
                      agreements.privacy
                        ? "bg-indigo-600 border-indigo-600"
                        : "border-gray-300 bg-white group-hover:border-indigo-400"
                    }`}
                  >
                    {agreements.privacy && (
                      <Check className="w-3.5 h-3.5 text-white" />
                    )}
                  </div>
                  <span
                    onClick={() =>
                      setAgreements((prev) => ({
                        ...prev,
                        privacy: !prev.privacy,
                      }))
                    }
                    className="font-bold text-gray-700"
                  >
                    동의합니다
                  </span>
                </label>
              </div>
            </div>
          </section>

          <hr className="border-gray-100" />

          {/* Section 2: Limitations */}
          <section className="space-y-3">
            <div className="flex items-start gap-4">
              <div className="mt-1 p-2 bg-orange-50 text-orange-600 rounded-lg shrink-0">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-bold text-gray-900 flex items-center gap-2">
                  ② 서비스 한계 및 법적 책임에 대한 인지 확인
                  <span className="px-2 py-0.5 bg-red-100 text-red-600 text-xs rounded-full font-bold">
                    필수
                  </span>
                </h3>

                <div className="mt-3 bg-gray-50 p-4 rounded-xl text-sm text-gray-600 leading-relaxed border border-gray-100">
                  <p className="font-bold text-gray-800 mb-2">
                    [서비스 한계 및 법적 책임에 대한 안내]
                  </p>
                  <p className="mb-2">
                    CheckMate는 계약 및 문서의 내용을 분석하여
                    <br />
                    <strong className="text-red-500">
                      잠재적인 위험 요소를 사전에 인지할 수 있도록 돕는 보조
                      도구
                    </strong>
                    입니다.
                  </p>
                  <p className="mb-2">본 서비스는 다음을 제공하지 않습니다.</p>
                  <ul className="list-disc pl-5 mb-2 space-y-1 text-gray-500">
                    <li>법률 자문 또는 법적 판단</li>
                    <li>계약 체결·해지에 대한 권고</li>
                    <li>법적 대리 행위</li>
                  </ul>
                  <p className="mt-2 text-gray-800 font-medium">
                    CheckMate에서 제공되는 정보는 참고용이며, 계약과 관련된{" "}
                    <strong className="text-red-600">
                      최종 판단 및 그에 따른 책임은 이용자 본인에게 있음
                    </strong>
                    을 안내드립니다.
                  </p>
                </div>

                <label className="flex items-center gap-2 mt-3 cursor-pointer group">
                  <div
                    onClick={() =>
                      setAgreements((prev) => ({
                        ...prev,
                        limitations: !prev.limitations,
                      }))
                    }
                    className={`w-5 h-5 rounded border flex items-center justify-center transition-all ${
                      agreements.limitations
                        ? "bg-indigo-600 border-indigo-600"
                        : "border-gray-300 bg-white group-hover:border-indigo-400"
                    }`}
                  >
                    {agreements.limitations && (
                      <Check className="w-3.5 h-3.5 text-white" />
                    )}
                  </div>
                  <span
                    onClick={() =>
                      setAgreements((prev) => ({
                        ...prev,
                        limitations: !prev.limitations,
                      }))
                    }
                    className="font-bold text-gray-700"
                  >
                    위 내용을 충분히 인지하였습니다
                  </span>
                </label>
              </div>
            </div>
          </section>

          <hr className="border-gray-100" />

          {/* Section 3: Prevention Purpose */}
          <section className="space-y-3">
            <div className="flex items-start gap-4">
              <div className="mt-1 p-2 bg-green-50 text-green-600 rounded-lg shrink-0">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-bold text-gray-900 flex items-center gap-2">
                  ③ 사전 예방 목적의 서비스 이용에 대한 인지 확인
                  <span className="px-2 py-0.5 bg-red-100 text-red-600 text-xs rounded-full font-bold">
                    필수
                  </span>
                </h3>

                <div className="mt-3 bg-gray-50 p-4 rounded-xl text-sm text-gray-600 leading-relaxed border border-gray-100">
                  <p className="font-bold text-gray-800 mb-2">
                    [사전 예방 목적의 서비스 이용 안내]
                  </p>
                  <p className="mb-2">
                    본 서비스는 분쟁이나 법적 문제 발생 이후의 해결을 목적으로
                    하지 않으며,
                    <br />
                    <strong className="text-indigo-600">
                      계약 체결 이전 단계에서 주의가 필요한 부분을 사전에
                      인지하도록 돕기 위한 목적
                    </strong>
                    으로 제공됩니다.
                  </p>
                  <p>
                    이용자는 CheckMate가 제공하는 정보가 위험 여부를 단정하거나
                    법적 효력을 갖는 판단이 아님을 인지하고, 이를{" "}
                    <strong className="text-gray-800">
                      보조적인 참고 정보로 활용함
                    </strong>
                    을 확인합니다.
                  </p>
                </div>

                <label className="flex items-center gap-2 mt-3 cursor-pointer group">
                  <div
                    onClick={() =>
                      setAgreements((prev) => ({
                        ...prev,
                        prevention: !prev.prevention,
                      }))
                    }
                    className={`w-5 h-5 rounded border flex items-center justify-center transition-all ${
                      agreements.prevention
                        ? "bg-indigo-600 border-indigo-600"
                        : "border-gray-300 bg-white group-hover:border-indigo-400"
                    }`}
                  >
                    {agreements.prevention && (
                      <Check className="w-3.5 h-3.5 text-white" />
                    )}
                  </div>
                  <span
                    onClick={() =>
                      setAgreements((prev) => ({
                        ...prev,
                        prevention: !prev.prevention,
                      }))
                    }
                    className="font-bold text-gray-700"
                  >
                    위 내용을 충분히 인지하였습니다
                  </span>
                </label>
              </div>
            </div>
          </section>
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-gray-100 bg-gray-50 flex items-center justify-between gap-4">
          <label className="flex items-center gap-2 cursor-pointer group">
            <div
              onClick={toggleAll}
              className={`w-6 h-6 rounded-md border-2 flex items-center justify-center transition-all ${
                isAllChecked
                  ? "bg-indigo-600 border-indigo-600"
                  : "border-gray-300 bg-white group-hover:border-gray-400"
              }`}
            >
              {isAllChecked && <Check className="w-4 h-4 text-white" />}
            </div>
            <span
              onClick={toggleAll}
              className="font-bold text-gray-900 text-lg"
            >
              모두 동의하기
            </span>
          </label>

          <button
            onClick={onConfirm}
            disabled={!isAllChecked}
            className={`px-8 py-3 rounded-xl font-bold text-white transition-all shadow-lg ${
              isAllChecked
                ? "bg-indigo-600 hover:bg-indigo-700 hover:scale-105 shadow-indigo-200"
                : "bg-gray-300 cursor-not-allowed shadow-none"
            }`}
          >
            확인 및 동의완료
          </button>
        </div>
      </div>
    </div>
  );
}

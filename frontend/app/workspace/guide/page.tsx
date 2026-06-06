import { GuideConnector } from "@/components/ApiPanels";
import { PageTitle, WorkspaceShell } from "@/components/WorkspaceShell";

export default function GuidePage() {
  return (
    <WorkspaceShell active="/workspace/guide">
      <PageTitle
        eyebrow="Workspace · Localization Guide"
        title="현지화 가이드"
        text="국가/장르 선택 또는 시놉시스 기반 국가 추천으로 API 가이드 섹션과 근거를 확인합니다."
      />
      <GuideConnector />
    </WorkspaceShell>
  );
}

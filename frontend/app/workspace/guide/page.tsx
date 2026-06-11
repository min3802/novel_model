import { GuideConnector } from "@/components/ApiPanels";
import { PageTitle, WorkspaceShell } from "@/components/WorkspaceShell";

export default function GuidePage() {
  return (
    <WorkspaceShell active="/workspace/guide">
      <PageTitle
        eyebrow="Workspace · Localization Guide"
        title="현지화 가이드"
        text="시놉시스가 있으면 먼저 국가 추천을 받고, 없으면 일본/중국/미국/태국 중 대상 국가를 직접 선택한 뒤 가이드를 생성합니다."
      />
      <GuideConnector />
    </WorkspaceShell>
  );
}

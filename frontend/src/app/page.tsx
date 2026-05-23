import dynamic from "next/dynamic";
const COPPage = dynamic(() => import("@/components/cop/COPPage"), { ssr: false });
export default function Home() { return <COPPage />; }

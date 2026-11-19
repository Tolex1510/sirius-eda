import type { Metadata } from "next";
import CsrMenu from "./CsrMenu";
export const metadata: Metadata = {
  title: "Меню: клиентская загрузка",
  robots: { index: false, follow: false },
};
export default function Page() {
  return <CsrMenu />;
}

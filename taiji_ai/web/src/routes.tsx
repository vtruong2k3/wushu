import type { RouteObject } from "react-router";

import { Layout } from "./components/Layout";
import { NotFoundPage } from "./pages/NotFoundPage";
import { StatusPage } from "./pages/StatusPage";

/** Route table shared by the app (browser router) and tests (memory router). */
export const routes: RouteObject[] = [
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <StatusPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];

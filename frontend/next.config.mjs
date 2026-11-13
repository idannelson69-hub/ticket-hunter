/** ממשק סטטי — נבנה לתיקיית out ומוגש ע"י שרת ה-FastAPI (אותו דומיין, בלי CORS) */
const nextConfig = {
  output: "export",
  images: { unoptimized: true },
  trailingSlash: false,
};
export default nextConfig;

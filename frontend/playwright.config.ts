import {defineConfig,devices} from "@playwright/test";
export default defineConfig({testDir:"./e2e",fullyParallel:false,retries:1,use:{baseURL:"http://localhost:3000",trace:"on-first-retry"},webServer:[{command:"npm run dev",url:"http://localhost:3000",reuseExistingServer:true},{command:"cd ../backend && uvicorn app.main:app --host 127.0.0.1 --port 8000",url:"http://localhost:8000/api/v1/health",reuseExistingServer:true}],projects:[{name:"chromium",use:{...devices["Desktop Chrome"]}}]});



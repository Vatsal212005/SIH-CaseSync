import {describe,expect,it,vi} from "vitest";
import {render} from "@testing-library/react";
import React from "react";
import CaseSyncApp from "@/components/casesync-app";

vi.mock("next/navigation",()=>({useRouter:()=>({push:vi.fn()})}));
describe("CaseSync application",()=>{
  it("shows the secure login experience when no session exists",async()=>{
    vi.stubGlobal("fetch",vi.fn().mockResolvedValue({ok:false,status:401,json:async()=>({detail:"Authentication required"})}));
    const view=render(<CaseSyncApp slug={[]}/>);
    expect(await view.findByText("Sign in to CaseSync")).toBeInTheDocument();
    expect(view.getByText(/Synthetic records only/i)).toBeInTheDocument();
  });
});



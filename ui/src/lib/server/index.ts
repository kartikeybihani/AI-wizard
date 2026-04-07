import { RunService } from "@/lib/server/run-service";

declare global {
  var __tomsRunService: RunService | undefined;
}

export function getRunService(): RunService {
  if (!global.__tomsRunService) {
    global.__tomsRunService = new RunService();
  }
  return global.__tomsRunService;
}

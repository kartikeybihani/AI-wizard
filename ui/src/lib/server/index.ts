import { MonitorService } from "@/lib/server/monitor-service";
import { RunService } from "@/lib/server/run-service";

declare global {
  var __tomsRunService: RunService | undefined;
  var __tomsMonitorService: MonitorService | undefined;
}

export function getRunService(): RunService {
  if (!global.__tomsRunService) {
    global.__tomsRunService = new RunService();
  }
  return global.__tomsRunService;
}

export function getMonitorService(): MonitorService {
  if (!global.__tomsMonitorService) {
    global.__tomsMonitorService = new MonitorService();
  }
  return global.__tomsMonitorService;
}

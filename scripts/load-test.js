import http from "k6/http";
import { check } from "k6";

const baseUrl = __ENV.BASE_URL || "http://127.0.0.1:8000";
const code = __ENV.CODE;

if (!code) {
  throw new Error("CODE is required, for example: CODE=abc123 k6 run scripts/load-test.js");
}

export const options = {
  scenarios: {
    redirect: {
      executor: "constant-arrival-rate",
      rate: Number(__ENV.RATE || 200),
      timeUnit: "1s",
      duration: __ENV.DURATION || "60s",
      preAllocatedVUs: Number(__ENV.PRE_ALLOCATED_VUS || 50),
      maxVUs: Number(__ENV.MAX_VUS || 200),
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.001"],
    http_req_duration: ["p(99)<100"],
  },
  summaryTrendStats: ["avg", "min", "med", "p(90)", "p(95)", "p(99)", "max"],
};

export default function () {
  const response = http.get(`${baseUrl}/${code}`, { redirects: 0 });
  check(response, {
    "status is 302": (result) => result.status === 302,
    "location is present": (result) => Boolean(result.headers.Location),
    "cache-control is no-store": (result) =>
      result.headers["Cache-Control"] === "no-store",
  });
}

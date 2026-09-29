async function runJobRequest(request, onMissing) {
  try {
    return await request();
  } catch (error) {
    if (error?.code !== "job_not_found") throw error;
    await onMissing();
    return null;
  }
}

export function getJobOrRecover(api, jobId, onMissing) {
  return runJobRequest(() => api.getJob(jobId), onMissing);
}

export function retryJobOrRecover(api, jobId, onMissing) {
  return runJobRequest(() => api.retryJob(jobId), onMissing);
}

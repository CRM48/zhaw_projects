#define _GNU_SOURCE

#include <pthread.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <sys/resource.h>

// Run the lock contention benchmark

enum lock_kind { LK_SPIN, LK_MUTEX, LK_ADAPTIVE };

static struct {
    enum lock_kind kind;
    int nthreads;
    long cs_ns;
    long samples;
    long warmup;
    int *cpus;
    int ncpus;
    const char *csv;
} cfg = { LK_MUTEX, 2, 500, 1000000, 10000, NULL, 0, NULL };

static void parse_cpus(const char *s) {
    char *copy = strdup(s);
    if (!copy) {
        perror("strdup");
        exit(1);
    }

    int count = 1;
    for (const char *p = s; *p; p++) {
        if (*p == ',') count++;
    }

    cfg.cpus = calloc((size_t)count, sizeof *cfg.cpus);
    if (!cfg.cpus) {
        perror("calloc");
        free(copy);
        exit(1);
    }

    char *save = NULL;
    for (char *tok = strtok_r(copy, ",", &save); tok; tok = strtok_r(NULL, ",", &save)) {
        char *end = NULL;
        long cpu = strtol(tok, &end, 10);

        if (end == tok || *end != '\0' || cpu < 0 || cpu >= CPU_SETSIZE) {
            fprintf(stderr, "Error: invalid CPU %s\n", tok);
            free(copy);
            exit(1);
        }

        cfg.cpus[cfg.ncpus++] = (int)cpu;
    }

    if (cfg.ncpus != count) {
        fprintf(stderr, "Error: invalid CPU list %s\n", s);
        free(copy);
        exit(1);
    }

    free(copy);
}

static void validate_config(void) {
    if (cfg.nthreads < 1) {
        fprintf(stderr, "Error: threads must be at least 1\n");
        exit(1);
    }

    if (cfg.cs_ns < 1) {
        fprintf(stderr, "Error: CS length must be at least 1ns\n");
        exit(1);
    }

    if (cfg.samples < cfg.nthreads) {
        fprintf(stderr, "Error: samples must be at least the thread count\n");
        exit(1);
    }

    if (cfg.warmup < 0) {
        fprintf(stderr, "Error: warmup must be at least 0\n");
        exit(1);
    }

    if (!cfg.cpus || cfg.ncpus < 1) {
        fprintf(stderr, "Error: CPU list is required\n");
        exit(1);
    }

    cpu_set_t allowed;
    if (sched_getaffinity(0, sizeof allowed, &allowed) != 0) {
        perror("sched_getaffinity");
        exit(1);
    }

    for (int i = 0; i < cfg.ncpus; i++) {
        if (!CPU_ISSET(cfg.cpus[i], &allowed)) {
            fprintf(stderr, "Error: CPU %d is not allowed\n", cfg.cpus[i]);
            exit(1);
        }

        for (int j = i + 1; j < cfg.ncpus; j++) {
            if (cfg.cpus[i] == cfg.cpus[j]) {
                fprintf(stderr, "Error: duplicate CPU %d\n", cfg.cpus[i]);
                exit(1);
            }
        }
    }
}

// Lock setup

static pthread_spinlock_t g_spin;
static pthread_mutex_t g_mutex;
static pthread_mutex_t g_adapt;

static inline void lock_acquire(void) {
    switch (cfg.kind) {
        case LK_SPIN:
            pthread_spin_lock(&g_spin);
            break;
        case LK_MUTEX:
            pthread_mutex_lock(&g_mutex);
            break;
        case LK_ADAPTIVE:
            pthread_mutex_lock(&g_adapt);
            break;
    }
}

static inline void lock_release(void) {
    switch (cfg.kind) {
        case LK_SPIN:
            pthread_spin_unlock(&g_spin);
            break;
        case LK_MUTEX:
            pthread_mutex_unlock(&g_mutex);
            break;
        case LK_ADAPTIVE:
            pthread_mutex_unlock(&g_adapt);
            break;
    }
}

static void locks_init(void) {
    int rc = pthread_spin_init(&g_spin, PTHREAD_PROCESS_PRIVATE);
    if (rc != 0) {
        fprintf(stderr, "Error: spinlock init failed: %s\n", strerror(rc));
        exit(1);
    }

    rc = pthread_mutex_init(&g_mutex, NULL);
    if (rc != 0) {
        fprintf(stderr, "Error: mutex init failed: %s\n", strerror(rc));
        exit(1);
    }

    pthread_mutexattr_t attr;
    rc = pthread_mutexattr_init(&attr);
    if (rc != 0) {
        fprintf(stderr, "Error: mutex attributes failed: %s\n", strerror(rc));
        exit(1);
    }

    rc = pthread_mutexattr_settype(&attr, PTHREAD_MUTEX_ADAPTIVE_NP);
    if (rc != 0) {
        fprintf(stderr, "Error: adaptive mutex is unavailable\n");
        exit(1);
    }

    rc = pthread_mutex_init(&g_adapt, &attr);
    if (rc != 0) {
        fprintf(stderr, "Error: adaptive mutex init failed: %s\n", strerror(rc));
        exit(1);
    }

    pthread_mutexattr_destroy(&attr);
}

// Timing and CS calibration

static uint64_t cs_spins_per_iter;
static uint64_t realised_cs_ns;

static inline uint64_t now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

static void report_timer(uint64_t *overhead_out) {
    struct timespec res;
    clock_getres(CLOCK_MONOTONIC, &res);

    enum { CAL = 1000000 };
    uint64_t t0 = now_ns();

    for (int i = 0; i < CAL; i++) {
        volatile uint64_t sink = now_ns();
        (void)sink;
    }

    uint64_t per_call = (now_ns() - t0) / CAL;
    *overhead_out = per_call;

    printf("# timer: CLOCK_MONOTONIC resolution=%ldns, clock_gettime overhead≈%luns\n", res.tv_nsec, (unsigned long)per_call);
}

static inline void busy_loop(uint64_t n) {
    for (volatile uint64_t i = 0; i < n; i++) {
        __asm__ __volatile__("" ::: "memory");
    }
}

static void calibrate_cs(void) {
    enum { PROBE = 50000000ull };
    uint64_t t0 = now_ns();

    busy_loop(PROBE);

    uint64_t dt = now_ns() - t0;
    double iters_per_ns = (double)PROBE / (double)dt;
    cs_spins_per_iter = (uint64_t)(iters_per_ns * (double)cfg.cs_ns);

    if (cs_spins_per_iter == 0) {
        cs_spins_per_iter = 1;
    }

    enum { VERIFY = 10000, VERIFY_REPEATS = 9 };
    uint64_t verify_results[VERIFY_REPEATS];

    for (int r = 0; r < VERIFY_REPEATS; r++) {
        t0 = now_ns();

        for (int i = 0; i < VERIFY; i++) {
            busy_loop(cs_spins_per_iter);
        }

        verify_results[r] = (now_ns() - t0) / VERIFY;
    }

    for (int i = 1; i < VERIFY_REPEATS; i++) {
        uint64_t value = verify_results[i];
        int j = i - 1;

        while (j >= 0 && verify_results[j] > value) {
            verify_results[j + 1] = verify_results[j];
            j--;
        }

        verify_results[j + 1] = value;
    }

    realised_cs_ns = verify_results[VERIFY_REPEATS / 2];

    printf("# cs: target=%ldns loop_iters=%lu realised≈%luns\n", cfg.cs_ns, (unsigned long)cs_spins_per_iter, (unsigned long)realised_cs_ns);
}

static void calibrate_on_measurement_cpu(uint64_t *timer_overhead) {
    cpu_set_t original;
    cpu_set_t set;

    if (sched_getaffinity(0, sizeof original, &original) != 0) {
        perror("sched_getaffinity");
        exit(1);
    }

    CPU_ZERO(&set);
    CPU_SET(cfg.cpus[0], &set);

    if (sched_setaffinity(0, sizeof set, &set) != 0) {
        perror("sched_setaffinity");
        exit(1);
    }

    if (sched_getcpu() != cfg.cpus[0]) {
        fprintf(stderr, "Error: calibration could not use CPU %d\n", cfg.cpus[0]);
        exit(1);
    }

    printf("# calibration CPU: %d\n", cfg.cpus[0]);

    report_timer(timer_overhead);
    calibrate_cs();

    if (sched_setaffinity(0, sizeof original, &original) != 0) {
        perror("sched_setaffinity");
        exit(1);
    }
}

// Worker threads

struct __attribute__((aligned(64))) worker {
    int id;
    int cpu;
    pthread_t tid;
    uint64_t *samples;
    long nsamples;
    long vcsw;
    long ivcsw;
    uint64_t measure_start_ns;
    uint64_t measure_end_ns;
};

static struct worker *workers;
static pthread_barrier_t start_barrier;
static pthread_barrier_t measure_barrier;

static long samples_for_worker(int id) {
    long base = cfg.samples / cfg.nthreads;
    long extra = cfg.samples % cfg.nthreads;
    return base + (id < extra ? 1 : 0);
}

static void *worker_fn(void *arg) {
    struct worker *w = (struct worker *)arg;

    cpu_set_t set;
    CPU_ZERO(&set);
    CPU_SET(w->cpu, &set);

    int rc = pthread_setaffinity_np(pthread_self(), sizeof set, &set);
    if (rc != 0) {
        fprintf(stderr, "Error: thread %d could not use CPU %d: %s\n", w->id, w->cpu, strerror(rc));
        exit(1);
    }

    if (sched_getcpu() != w->cpu) {
        fprintf(stderr, "Error: thread %d is on the wrong CPU\n", w->id);
        exit(1);
    }

    pthread_barrier_wait(&start_barrier);

    for (long i = 0; i < cfg.warmup; i++) {
        lock_acquire();
        busy_loop(cs_spins_per_iter);
        lock_release();
    }

    pthread_barrier_wait(&measure_barrier);

    struct rusage before;
    struct rusage after;

    if (getrusage(RUSAGE_THREAD, &before) != 0) {
        perror("getrusage");
        exit(1);
    }

    w->measure_start_ns = now_ns();

    for (long i = 0; i < w->nsamples; i++) {
        uint64_t t0 = now_ns();
        lock_acquire();
        uint64_t t1 = now_ns();

        busy_loop(cs_spins_per_iter);
        lock_release();

        w->samples[i] = t1 - t0;
    }

    w->measure_end_ns = now_ns();

    if (getrusage(RUSAGE_THREAD, &after) != 0) {
        perror("getrusage");
        exit(1);
    }

    w->vcsw = after.ru_nvcsw - before.ru_nvcsw;
    w->ivcsw = after.ru_nivcsw - before.ru_nivcsw;

    return NULL;
}

// Results

static int cmp_u64(const void *a, const void *b) {
    uint64_t x = *(const uint64_t *)a;
    uint64_t y = *(const uint64_t *)b;
    return (x > y) - (x < y);
}

static uint64_t pct(uint64_t *sorted, long n, double p) {
    long idx = (long)(p * (double)(n - 1));
    return sorted[idx];
}

static const char *kind_name(void) {
    if (cfg.kind == LK_SPIN) return "spin";
    if (cfg.kind == LK_MUTEX) return "mutex";
    return "adaptive";
}

static void usage(const char *argv0) {
    fprintf(stderr, "usage: %s [--lock spin|mutex|adaptive] [--threads N] [--cpus LIST] [--cs-ns NS] [--samples N] [--warmup N] [--csv FILE]\n", argv0);
    exit(2);
}

int main(int argc, char **argv) {
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--lock") && i + 1 < argc) {
            const char *value = argv[++i];

            if (!strcmp(value, "spin")) cfg.kind = LK_SPIN;
            else if (!strcmp(value, "mutex")) cfg.kind = LK_MUTEX;
            else if (!strcmp(value, "adaptive")) cfg.kind = LK_ADAPTIVE;
            else usage(argv[0]);
        } else if (!strcmp(argv[i], "--threads") && i + 1 < argc) {
            cfg.nthreads = atoi(argv[++i]);
        } else if (!strcmp(argv[i], "--cpus") && i + 1 < argc) {
            parse_cpus(argv[++i]);
        } else if (!strcmp(argv[i], "--cs-ns") && i + 1 < argc) {
            cfg.cs_ns = atol(argv[++i]);
        } else if (!strcmp(argv[i], "--samples") && i + 1 < argc) {
            cfg.samples = atol(argv[++i]);
        } else if (!strcmp(argv[i], "--warmup") && i + 1 < argc) {
            cfg.warmup = atol(argv[++i]);
        } else if (!strcmp(argv[i], "--csv") && i + 1 < argc) {
            cfg.csv = argv[++i];
        } else {
            usage(argv[0]);
        }
    }

    validate_config();

    if (cfg.nthreads > cfg.ncpus) {
        fprintf(stderr, "Warning: %d threads on %d CPUs - oversubscribed (H5 regime)\n", cfg.nthreads, cfg.ncpus);
    }

    uint64_t timer_overhead;
    calibrate_on_measurement_cpu(&timer_overhead);
    locks_init();

    workers = calloc((size_t)cfg.nthreads, sizeof *workers);
    if (!workers) {
        perror("calloc");
        return 1;
    }

    int rc = pthread_barrier_init(&start_barrier, NULL, (unsigned)cfg.nthreads);
    if (rc != 0) {
        fprintf(stderr, "Error: start barrier failed: %s\n", strerror(rc));
        return 1;
    }

    rc = pthread_barrier_init(&measure_barrier, NULL, (unsigned)cfg.nthreads);
    if (rc != 0) {
        fprintf(stderr, "Error: measurement barrier failed: %s\n", strerror(rc));
        return 1;
    }

    for (int i = 0; i < cfg.nthreads; i++) {
        workers[i].id = i;
        workers[i].cpu = cfg.cpus[i % cfg.ncpus];
        workers[i].nsamples = samples_for_worker(i);
        workers[i].samples = malloc((size_t)workers[i].nsamples * sizeof(uint64_t));

        if (!workers[i].samples) {
            perror("malloc");
            return 1;
        }
    }

    for (int i = 0; i < cfg.nthreads; i++) {
        rc = pthread_create(&workers[i].tid, NULL, worker_fn, &workers[i]);
        if (rc != 0) {
            fprintf(stderr, "Error: thread %d could not start: %s\n", i, strerror(rc));
            exit(1);
        }
    }

    for (int i = 0; i < cfg.nthreads; i++) {
        rc = pthread_join(workers[i].tid, NULL);
        if (rc != 0) {
            fprintf(stderr, "Error: thread %d could not join: %s\n", i, strerror(rc));
            exit(1);
        }
    }

    uint64_t wall_start = workers[0].measure_start_ns;
    uint64_t wall_end = workers[0].measure_end_ns;

    for (int i = 1; i < cfg.nthreads; i++) {
        if (workers[i].measure_start_ns < wall_start) wall_start = workers[i].measure_start_ns;
        if (workers[i].measure_end_ns > wall_end) wall_end = workers[i].measure_end_ns;
    }

    uint64_t wall_ns = wall_end - wall_start;

    long total = cfg.samples;
    uint64_t *all = malloc((size_t)total * sizeof(uint64_t));
    if (!all) {
        perror("malloc");
        return 1;
    }

    long k = 0;

    for (int i = 0; i < cfg.nthreads; i++) {
        memcpy(all + k, workers[i].samples, (size_t)workers[i].nsamples * sizeof(uint64_t));
        k += workers[i].nsamples;
    }

    if (k != total) {
        fprintf(stderr, "Error: sample count is %ld, expected %ld\n", k, total);
        return 1;
    }

    qsort(all, (size_t)total, sizeof(uint64_t), cmp_u64);

    printf("\np50=%lu p90=%lu p99=%lu p999=%lu min=%lu max=%lu\n", (unsigned long)pct(all, total, 0.50), (unsigned long)pct(all, total, 0.90), (unsigned long)pct(all, total, 0.99), (unsigned long)pct(all, total, 0.999), (unsigned long)all[0], (unsigned long)all[total - 1]);

    printf("# realised critical-section length: %luns (target=%ldns)\n", (unsigned long)realised_cs_ns, cfg.cs_ns);
    printf("# plausibility throughput: %.0f acquisitions/s (measured phase only)\n", (double)total / ((double)wall_ns / 1e9));

    for (int i = 0; i < cfg.nthreads; i++) {
        printf("# thread %d: cpu=%d acquisitions=%ld voluntary_ctxsw=%ld involuntary_ctxsw=%ld\n", i, workers[i].cpu, workers[i].nsamples, workers[i].vcsw, workers[i].ivcsw);
    }

    if (cfg.nthreads > cfg.ncpus) {
        printf("# NOTE: scheduler context switches are expected by design\n");
    }

    if (cfg.csv) {
        FILE *f = fopen(cfg.csv, "w");
        if (!f) {
            perror("csv");
            return 1;
        }

        fprintf(f, "lock,threads,cs_ns,cs_realised_ns,thread_id,cpu_id,sample_idx,latency_ns\n");

        for (int i = 0; i < cfg.nthreads; i++) {
            for (long j = 0; j < workers[i].nsamples; j++) {
                fprintf(f, "%s,%d,%ld,%lu,%d,%d,%ld,%lu\n", kind_name(), cfg.nthreads, cfg.cs_ns, (unsigned long)realised_cs_ns, i, workers[i].cpu, j, (unsigned long)workers[i].samples[j]);
            }
        }

        fclose(f);
        printf("# raw samples written to %s\n", cfg.csv);
    }

    free(all);

    for (int i = 0; i < cfg.nthreads; i++) {
        free(workers[i].samples);
    }

    free(workers);
    free(cfg.cpus);

    pthread_barrier_destroy(&start_barrier);
    pthread_barrier_destroy(&measure_barrier);
    pthread_spin_destroy(&g_spin);
    pthread_mutex_destroy(&g_mutex);
    pthread_mutex_destroy(&g_adapt);

    return 0;
}

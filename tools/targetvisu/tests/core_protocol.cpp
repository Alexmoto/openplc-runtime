// SPDX-License-Identifier: GPL-3.0-only
// Links the real debug handler + write journal against a fake IEC program.
extern "C" {
#include "debug_handler.h"
}
#include "debug_write_journal.h"
#include "image_tables.h"
#include "plc_state_manager.h"
#include "journal_buffer.h"
#include "utils/utils.h"
#include <cassert>
#include <cstring>
#include <cstdio>
#include <vector>

static float value = 12.5f;
static int writes = 0, forces = 0;
static bool input = false;
static PLCState state = PLC_STATE_RUNNING;
static pthread_mutex_t mutex = PTHREAD_MUTEX_INITIALIZER;
static char identity[] = "0123456789abcdef0123456789abcdef";
extern "C" {
char *ext_strucpp_program_md5 = identity;
unsigned long scan_counter = 123;
static uint8_t arrays() { return 1; }
static uint16_t elems(uint8_t) { return 1; }
static uint16_t size(uint8_t, uint16_t) { return 4; }
static uint16_t debug_read(uint8_t, uint16_t, uint8_t *dest) { memcpy(dest, &value, 4); return 4; }
static uint8_t debug_write(uint8_t, uint16_t, const uint8_t *bytes, uint16_t len) {
    assert(len == 4); memcpy(&value, bytes, 4); ++writes; return 0x7e;
}
static uint8_t force(uint8_t, uint16_t, bool, const uint8_t *, uint16_t) { ++forces; return 0x7e; }
static int locate(uint8_t, uint16_t, uint8_t *area, uint8_t *, uint16_t *, uint8_t *) { *area = 0; return input; }
uint8_t (*ext_strucpp_debug_array_count)(void) = arrays;
uint16_t (*ext_strucpp_debug_elem_count)(uint8_t) = elems;
uint16_t (*ext_strucpp_debug_size)(uint8_t,uint16_t) = size;
uint16_t (*ext_strucpp_debug_read)(uint8_t,uint16_t,uint8_t*) = debug_read;
uint8_t (*ext_strucpp_debug_write)(uint8_t,uint16_t,const uint8_t*,uint16_t) = debug_write;
uint8_t (*ext_strucpp_debug_set)(uint8_t,uint16_t,bool,const uint8_t*,uint16_t) = force;
int (*ext_strucpp_debug_locate)(uint8_t,uint16_t,uint8_t*,uint8_t*,uint16_t*,uint8_t*) = locate;
PLCState plc_get_state() { return state; }
pthread_mutex_t *image_tables_mutex() { return &mutex; }
void log_debug(const char *, ...) {}
void log_error(const char *, ...) {}
void log_warn(const char *, ...) {}
int journal_write_bool(journal_buffer_type_t,uint16_t,uint8_t,bool) { return 0; }
int journal_write_byte(journal_buffer_type_t,uint16_t,uint8_t) { return 0; }
int journal_write_int(journal_buffer_type_t,uint16_t,uint16_t) { return 0; }
int journal_write_dint(journal_buffer_type_t,uint16_t,uint32_t) { return 0; }
int journal_write_lint(journal_buffer_type_t,uint16_t,uint64_t) { return 0; }
void journal_force_set(journal_buffer_type_t,uint16_t,uint8_t,uint64_t) {}
void journal_force_clear(journal_buffer_type_t,uint16_t,uint8_t) {}
}
static std::vector<uint8_t> request(std::vector<uint8_t> p) {
    uint8_t frame[4096] = {}; memcpy(frame, p.data(), p.size());
    size_t n = process_debug_data(frame, p.size()); return {frame, frame+n};
}
static std::vector<uint8_t> prefix(uint8_t fc) {
    std::vector<uint8_t> p{fc}; p.insert(p.end(), identity, identity+32); return p;
}
int main() {
    auto meta = request({0x52}); assert(meta.size() == 36 && meta[1] == 0x7e);
    auto r = prefix(0x50); r.insert(r.end(), {0,1,0,0,0});
    auto response = request(r); assert(response.size() == 14 && response[0] == 0x50 && response[1] == 0x7e);
    float decoded; memcpy(&decoded, response.data()+10, 4); assert(decoded == value);
    auto w = prefix(0x51); w.insert(w.end(), {0,0,0,0,4});
    float desired = 42.0f; auto bytes = reinterpret_cast<uint8_t*>(&desired); w.insert(w.end(), bytes, bytes+4);
    assert(request(w)[1] == 0x7e && value == 12.5f); // queued, no write on socket thread
    debug_write_journal_drain(); assert(value == 42 && writes == 1 && forces == 0);
    state = PLC_STATE_STOPPED; assert(request(w)[1] == 0x84); state = PLC_STATE_RUNNING;
    auto bad = w; bad[1] = 'x'; assert(request(bad)[1] == 0x85);
    bad = w; bad[33] = 9; assert(request(bad)[1] == 0x81);
    bad = w; bad[37] = 3; assert(request(bad)[1] == 0x81);
    input = true; assert(request(w)[1] == 0x86); input = false;
    assert(request(w)[1] == 0x7e); identity[0] = 'f'; debug_write_journal_drain(); assert(writes == 1); identity[0] = '0';
    // Every truncated prefix must fail without touching the program.
    for (size_t n=1;n<w.size();++n) assert(request({w.begin(),w.begin()+n})[1] != 0x7e);
    for (int n=0;n<128;++n) assert(request(w)[1] == 0x7e);
    assert(request(w)[1] == 0x82); debug_write_journal_reset();
    assert(writes == 1 && forces == 0);
    puts("TargetVisu core protocol / real queue: PASS");
}

# =========================================================================
#   Unity - A Test Framework for C
#   ThrowTheSwitch.org
#   Copyright (c) 2007-26 Mike Karlesky, Mark VanderVoord, & Greg Williams
#   SPDX-License-Identifier: MIT
# =========================================================================

require 'fileutils'
require_relative '../../auto/colour_reporter'

# the 'test:scripts' rake task tallies these, so only initialize them if we are loaded first
$generate_test_runner_tests ||= 0
$generate_test_runner_failures ||= 0
$unity_test_summary_failures = 0

SUMMARY_SCRIPT  = File.expand_path('../../auto/unity_test_summary.rb', __dir__)
SUMMARY_SANDBOX = File.expand_path('../sandbox/test_summary', __dir__)
SUMMARY_RESULTS = <<~RESULTS
  test/test_a.c:12:test_thing:PASS
  test/test_b.c:34:test_broken:FAIL: Expected 1 Was 2
  test/test_c.c:56:test_skipped:IGNORE: not ready

  -----------------------
  3 Tests 1 Failures 1 Ignored
RESULTS

def summary_test(name, passed)
  if passed
    report "#{name}:PASS"
  else
    report "#{name}:FAIL"
    $generate_test_runner_failures += 1
    $unity_test_summary_failures += 1
  end
  $generate_test_runner_tests += 1
end

FileUtils.rm_rf(SUMMARY_SANDBOX)
FileUtils.mkdir_p(SUMMARY_SANDBOX)
File.write(File.join(SUMMARY_SANDBOX, 'test_sample.testfail'), SUMMARY_RESULTS)

begin
  Dir.chdir(SUMMARY_SANDBOX) do
    # with no arguments at all, the result files are looked for in the current directory
    output = `ruby "#{SUMMARY_SCRIPT}" 2>&1`
    summary_test('UnityTestSummary_DefaultsResultDirectoryToCurrentDirectory',
                 $?.success? && output.include?('3 TOTAL TESTS 1 TOTAL FAILURES 1 IGNORED'))

    # with only a result directory given, the root path defaults to the current directory
    expected = "#{Dir.pwd}/test/test_b.c:34".tr('/', '\\')
    output = `ruby "#{SUMMARY_SCRIPT}" ./ 2>&1`
    summary_test('UnityTestSummary_DefaultsRootPathToCurrentDirectory', output.include?(expected))
  end
ensure
  FileUtils.rm_rf(SUMMARY_SANDBOX)
end

raise "There were #{$unity_test_summary_failures} failures while testing unity_test_summary.rb" if $unity_test_summary_failures > 0

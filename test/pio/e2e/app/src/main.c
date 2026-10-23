/*
 * Prints demo's answer: 52 once CI has set DEMO_PLUS to 12 in demo's
 * configuration header and installed again, which shows the update kept it.
 * And flags', 7 from its pio.project.build_flags, which flags.h checks
 * reached this file too.
 */

#include <stdio.h>
#include "demo.h"
#include "flags.h"

int main(void)
{
    printf("demo says %d, flags say %d\n", demo_answer(), flags_answer());

    return 0;
}

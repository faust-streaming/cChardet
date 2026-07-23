/* -*- Mode: C++; tab-width: 2; indent-tabs-mode: nil; c-basic-offset: 2 -*- */
/* ***** BEGIN LICENSE BLOCK *****
 * Version: MPL 1.1/GPL 2.0/LGPL 2.1
 *
 * The contents of this file are subject to the Mozilla Public License Version
 * 1.1 (the "License"); you may not use this file except in compliance with
 * the License. You may obtain a copy of the License at
 * http://www.mozilla.org/MPL/
 *
 * Software distributed under the License is distributed on an "AS IS" basis,
 * WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License
 * for the specific language governing rights and limitations under the
 * License.
 *
 * The Original Code is Mozilla Universal charset detector code.
 *
 * The Initial Developer of the Original Code is
 * Netscape Communications Corporation.
 * Portions created by the Initial Developer are Copyright (C) 2001
 * the Initial Developer. All Rights Reserved.
 *
 * Contributor(s):
 *          Shy Shalom <shooshX@gmail.com>
 *          Proofpoint, Inc.
 *
 * Alternatively, the contents of this file may be used under the terms of
 * either the GNU General Public License Version 2 or later (the "GPL"), or
 * the GNU Lesser General Public License Version 2.1 or later (the "LGPL"),
 * in which case the provisions of the GPL or the LGPL are applicable instead
 * of those above. If you wish to allow use of your version of this file only
 * under the terms of either the GPL or the LGPL, and not to allow others to
 * use your version of this file under the terms of the MPL, indicate your
 * decision by deleting the provisions above and replace them with the notice
 * and other provisions required by the GPL or the LGPL. If you do not delete
 * the provisions above, a recipient may use your version of this file under
 * the terms of any one of the MPL, the GPL or the LGPL.
 *
 * ***** END LICENSE BLOCK ***** */

/*
 * cChardet uchardet overlay
 *
 * freedesktop uchardet's multibyte group decodes every candidate to Unicode
 * and fans those code points out to every generic language detector. cChardet
 * exposes only encoding and confidence, so this replacement keeps the charset
 * probers and their native confidence while skipping the generic language
 * pass. The upstream class ABI remains unchanged.
 */

#include <stdint.h>
#include <stdio.h>

#include "nsMBCSGroupProber.h"
#include "nsUniversalDetector.h"

/*
 * Upstream relies on the generic language models to discard a UTF-8
 * candidate produced from non-UTF-8 input: nsUTF8Prober never rejects
 * invalid byte sequences itself and its confidence floor (0.5) always
 * clears CANDIDATE_THRESHOLD. Without the language pass, this overlay must
 * disqualify the UTF-8 prober directly, so it runs a strict incremental
 * UTF-8 validity DFA over the raw stream.
 *
 * DFA states: 0 expects a lead byte; 1-3 expect that many unconstrained
 * continuation bytes; 4-7 expect the range-restricted first continuation
 * byte after E0/ED/F0/F4. UTF8_DFA_INVALID is sticky.
 */
#define UTF8_DFA_INVALID 0x100u

static unsigned int
Utf8DfaAdvance(unsigned int state, unsigned char byte)
{
  switch (state)
  {
    case 0:
      if (byte < 0x80) return 0;
      if (byte >= 0xC2 && byte <= 0xDF) return 1;
      if (byte == 0xE0) return 4;
      if ((byte >= 0xE1 && byte <= 0xEC) || byte == 0xEE || byte == 0xEF)
        return 2;
      if (byte == 0xED) return 5;
      if (byte == 0xF0) return 6;
      if (byte >= 0xF1 && byte <= 0xF3) return 3;
      if (byte == 0xF4) return 7;
      return UTF8_DFA_INVALID;
    case 1: return (byte >= 0x80 && byte <= 0xBF) ? 0 : UTF8_DFA_INVALID;
    case 2: return (byte >= 0x80 && byte <= 0xBF) ? 1 : UTF8_DFA_INVALID;
    case 3: return (byte >= 0x80 && byte <= 0xBF) ? 2 : UTF8_DFA_INVALID;
    case 4: return (byte >= 0xA0 && byte <= 0xBF) ? 1 : UTF8_DFA_INVALID;
    case 5: return (byte >= 0x80 && byte <= 0x9F) ? 1 : UTF8_DFA_INVALID;
    case 6: return (byte >= 0x90 && byte <= 0xBF) ? 2 : UTF8_DFA_INVALID;
    case 7: return (byte >= 0x80 && byte <= 0x8F) ? 2 : UTF8_DFA_INVALID;
    default: return UTF8_DFA_INVALID;
  }
}

/*
 * The upstream header is not overlaid, so the class layout cannot grow a
 * new member. The overlay never instantiates language detectors, which
 * leaves every langDetectors slot permanently null; the first slot is
 * repurposed to carry the DFA state as a pointer-sized integer. It is
 * never dereferenced and never reaches upstream code.
 */
static inline bool
Utf8IsInvalid(nsLanguageDetector* slot)
{
  return ((uintptr_t) slot) & UTF8_DFA_INVALID;
}

#if defined(DEBUG_chardet) || defined(DEBUG_jgmyers)
const char *ProberName[] =
{
  "UTF-8",
  "SJIS",
  "EUC-JP",
  "GB18030",
  "EUC-KR",
  "Big5",
  "EUC-TW",
  "Johab"
};
#endif

#define CANDIDATE_THRESHOLD 0.3f
#define CODE_POINT_BUFFER_SIZE 1024

/*
 * Upstream multiplies each multibyte prober's confidence by a language-model
 * confidence before comparing against CANDIDATE_THRESHOLD, which suppresses
 * false positives such as Big5 claiming a near-ASCII Windows-1252 file with
 * conf ~0.4 (issue #33). Without the language pass, non-UTF-8 multibyte
 * probers need strong distribution evidence on their own: genuine detections
 * score >= ~0.7 while such false positives stay around 0.4.
 */
#define MBCS_CANDIDATE_THRESHOLD 0.5f

/*
 * When the stream is not valid UTF-8 the UTF-8 prober is kept only as a
 * last-resort candidate with this fixed confidence. The value sits above
 * nsUniversalDetector's MINIMUM_THRESHOLD (0.20), so the guess survives for
 * near-ASCII data no other prober claims (mirroring upstream, whose
 * language pass also leaves a weak UTF-8 guess there), and below
 * CANDIDATE_THRESHOLD (0.30), so it can never outrank any other reported
 * candidate.
 */
#define UTF8_INVALID_CONFIDENCE 0.25f

static nsProbingState
HandleCharsetData(nsCharSetProber* prober,
                  const char* data,
                  PRUint32 length,
                  int** codePointBuffer,
                  int* codePointBufferIdx,
                  int codePointBufferSize)
{
  nsProbingState state = eDetecting;

  if (!codePointBuffer)
    return prober->HandleData(data, length, NULL, NULL);

  /*
   * The charset probers write decoded code points into the caller-owned
   * buffer. We intentionally discard those values, but still provide bounded
   * storage because the probers require it. Splitting by bytes is safe:
   * their state machines preserve incomplete multibyte sequences across calls,
   * and the number of emitted code points cannot exceed the input byte count.
   */
  PRUint32 offset = 0;
  while (offset < length)
  {
    PRUint32 chunkLength = length - offset;
    if (chunkLength > (PRUint32) codePointBufferSize)
      chunkLength = (PRUint32) codePointBufferSize;

    *codePointBufferIdx = 0;
    state = prober->HandleData(data + offset, chunkLength,
                               codePointBuffer, codePointBufferIdx);
    *codePointBufferIdx = 0;

    if (state != eDetecting)
      break;
    offset += chunkLength;
  }

  return state;
}

nsMBCSGroupProber::nsMBCSGroupProber(PRUint32 aLanguageFilter)
{
  for (PRUint32 i = 0; i < NUM_OF_PROBERS; i++)
  {
    mProbers[i] = nsnull;
    mIsActive[i] = PR_FALSE;
    codePointBuffer[i] = nsnull;
    codePointBufferSize[i] = 0;
    codePointBufferIdx[i] = 0;

    for (PRUint32 j = 0; j < NUM_OF_LANGUAGES; j++)
    {
      candidates[i][j] = false;
      langDetectors[i][j] = nsnull;
    }
  }

  mProbers[0] = new nsUTF8Prober();
  if (aLanguageFilter & NS_FILTER_JAPANESE)
  {
    mProbers[1] = new nsSJISProber(aLanguageFilter == NS_FILTER_JAPANESE);
    mProbers[2] = new nsEUCJPProber(aLanguageFilter == NS_FILTER_JAPANESE);
  }
  if (aLanguageFilter & NS_FILTER_CHINESE_SIMPLIFIED)
    mProbers[3] = new nsGB18030Prober(aLanguageFilter == NS_FILTER_CHINESE_SIMPLIFIED);
  if (aLanguageFilter & NS_FILTER_KOREAN)
  {
    mProbers[4] = new nsEUCKRProber(aLanguageFilter == NS_FILTER_KOREAN);
    mProbers[7] = new nsJohabProber(aLanguageFilter == NS_FILTER_KOREAN);
  }
  if (aLanguageFilter & NS_FILTER_CHINESE_TRADITIONAL)
  {
    mProbers[5] = new nsBig5Prober(aLanguageFilter == NS_FILTER_CHINESE_TRADITIONAL);
    mProbers[6] = new nsEUCTWProber(aLanguageFilter == NS_FILTER_CHINESE_TRADITIONAL);
  }

  Reset();
}

nsMBCSGroupProber::~nsMBCSGroupProber()
{
  for (PRUint32 i = 0; i < NUM_OF_PROBERS; i++)
  {
    delete mProbers[i];
    delete [] codePointBuffer[i];
  }
}

void nsMBCSGroupProber::Reset(void)
{
  mActiveNum = 0;
  for (PRUint32 i = 0; i < NUM_OF_PROBERS; i++)
  {
    if (mProbers[i])
    {
      mProbers[i]->Reset();
      mIsActive[i] = PR_TRUE;
      ++mActiveNum;

      if (mProbers[i]->DecodeToUnicode() && !codePointBuffer[i])
      {
        codePointBufferSize[i] = CODE_POINT_BUFFER_SIZE;
        codePointBuffer[i] = new int[codePointBufferSize[i]];
      }
      codePointBufferIdx[i] = 0;
    }
    else
    {
      mIsActive[i] = PR_FALSE;
    }

    for (PRUint32 j = 0; j < NUM_OF_LANGUAGES; j++)
      candidates[i][j] = false;
  }

  langDetectors[0][0] = nsnull;  /* clear the UTF-8 validity DFA state */
  mState = eDetecting;
  mKeepNext = 0;
}

nsProbingState nsMBCSGroupProber::HandleData(const char* aBuf, PRUint32 aLen,
                                             int** cpBuffer,
                                             int* cpBufferIdx)
{
  nsProbingState state;
  PRUint32 start = 0;
  PRUint32 keepNext = mKeepNext;

  (void) cpBuffer;
  (void) cpBufferIdx;

  /* Track UTF-8 validity over the raw stream before any filtering. Any
   * pure-ASCII prefix the universal detector skipped is trivially valid,
   * so starting at the first high byte gives the same verdict. */
  if (mIsActive[0] && !Utf8IsInvalid(langDetectors[0][0]))
  {
    unsigned int dfa = (unsigned int)(uintptr_t) langDetectors[0][0];
    for (PRUint32 pos = 0; pos < aLen && dfa != UTF8_DFA_INVALID; ++pos)
      dfa = Utf8DfaAdvance(dfa, (unsigned char) aBuf[pos]);
    langDetectors[0][0] = (nsLanguageDetector*)(uintptr_t) dfa;
  }

  /* Preserve uchardet's high-byte filtering. */
  for (PRUint32 pos = 0; pos < aLen; ++pos)
  {
    if (aBuf[pos] & 0x80)
    {
      if (!keepNext)
        start = pos;
      keepNext = 2;
    }
    else if (keepNext && --keepNext == 0)
    {
      for (PRUint32 i = 0; i < NUM_OF_PROBERS; i++)
      {
        if (!mIsActive[i])
          continue;

        state = HandleCharsetData(
          mProbers[i], aBuf + start, pos + 1 - start,
          codePointBuffer[i] ? &(codePointBuffer[i]) : NULL,
          codePointBuffer[i] ? &(codePointBufferIdx[i]) : NULL,
          codePointBufferSize[i]);

        if (state == eFoundIt &&
            (i != 0 || !Utf8IsInvalid(langDetectors[0][0])) &&
            mProbers[i]->GetConfidence(0) >
              (i == 0 ? CANDIDATE_THRESHOLD : MBCS_CANDIDATE_THRESHOLD))
        {
          mState = eFoundIt;
          return mState;
        }
      }
    }
  }

  if (keepNext)
  {
    for (PRUint32 i = 0; i < NUM_OF_PROBERS; i++)
    {
      if (!mIsActive[i])
        continue;

      state = HandleCharsetData(
        mProbers[i], aBuf + start, aLen - start,
        codePointBuffer[i] ? &(codePointBuffer[i]) : NULL,
        codePointBuffer[i] ? &(codePointBufferIdx[i]) : NULL,
        codePointBufferSize[i]);

      if (state == eFoundIt &&
          (i != 0 || !Utf8IsInvalid(langDetectors[0][0])) &&
          mProbers[i]->GetConfidence(0) >
            (i == 0 ? CANDIDATE_THRESHOLD : MBCS_CANDIDATE_THRESHOLD))
      {
        mState = eFoundIt;
        return mState;
      }
    }
  }

  mKeepNext = keepNext;
  return mState;
}

void nsMBCSGroupProber::CheckCandidates()
{
  for (PRUint32 i = 0; i < NUM_OF_PROBERS; i++)
  {
    for (PRUint32 j = 0; j < NUM_OF_LANGUAGES; j++)
      candidates[i][j] = false;

    if (!mIsActive[i])
      continue;

    if (i == 0)
      /* Invalid UTF-8 stays listed as a penalized last-resort fallback. */
      candidates[0][0] = Utf8IsInvalid(langDetectors[0][0]) ||
        (mProbers[0]->GetConfidence(0) > CANDIDATE_THRESHOLD);
    else
      candidates[i][0] =
        (mProbers[i]->GetConfidence(0) > MBCS_CANDIDATE_THRESHOLD);
  }
}

int nsMBCSGroupProber::GetCandidates()
{
  int numCandidates = 0;

  CheckCandidates();
  for (PRUint32 i = 0; i < NUM_OF_PROBERS; i++)
    if (candidates[i][0])
      numCandidates++;

  return numCandidates;
}

const char* nsMBCSGroupProber::GetCharSetName(int candidate)
{
  int numCandidates = GetCandidates();
  int candidateIt = 0;

  if (numCandidates == 0)
    return NULL;
  if (candidate < 0 || candidate >= numCandidates)
    candidate = 0;

  for (PRUint32 i = 0; i < NUM_OF_PROBERS; i++)
  {
    if (!candidates[i][0])
      continue;
    if (candidate == candidateIt)
      return mProbers[i]->GetCharSetName(0);
    candidateIt++;
  }

  return NULL;
}

const char* nsMBCSGroupProber::GetLanguage(int candidate)
{
  (void) candidate;
  return NULL;
}

float nsMBCSGroupProber::GetConfidence(int candidate)
{
  int numCandidates = GetCandidates();
  int candidateIt = 0;

  if (numCandidates == 0)
    return 0.0;
  if (candidate < 0 || candidate >= numCandidates)
    candidate = 0;

  if (mState == eNotMe)
    return 0.01f;

  for (PRUint32 i = 0; i < NUM_OF_PROBERS; i++)
  {
    if (!candidates[i][0])
      continue;
    if (candidate == candidateIt)
    {
      if (i == 0 && Utf8IsInvalid(langDetectors[0][0]))
        return UTF8_INVALID_CONFIDENCE;
      return mProbers[i]->GetConfidence(0);
    }
    candidateIt++;
  }

  return 0.0;
}

#ifdef DEBUG_chardet
void nsMBCSGroupProber::DumpStatus()
{
  GetCandidates();
  for (PRUint32 i = 0; i < NUM_OF_PROBERS; i++)
  {
    if (!mIsActive[i])
      printf("  MBCS inactive: [%s] (confidence is too low).\r\n", ProberName[i]);
    else
      printf("  MBCS %1.3f: [%s]\r\n",
             mProbers[i]->GetConfidence(0), ProberName[i]);
  }
}
#endif

#ifdef DEBUG_jgmyers
void nsMBCSGroupProber::GetDetectorState(
  nsUniversalDetector::DetectorState (&states)[nsUniversalDetector::NumDetectors],
  PRUint32 &offset)
{
  for (PRUint32 i = 0; i < NUM_OF_PROBERS; ++i)
  {
    states[offset].name = ProberName[i];
    states[offset].isActive = mIsActive[i];
    states[offset].confidence =
      mIsActive[i] ? mProbers[i]->GetConfidence(0) : 0.0;
    ++offset;
  }
}
#endif /* DEBUG_jgmyers */

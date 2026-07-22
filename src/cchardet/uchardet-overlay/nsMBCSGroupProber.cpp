/* -*- Mode: C++; tab-width: 2; indent-tabs-mode: nil; c-basic-offset: 2 -*- */
/* SPDX-License-Identifier: MPL-1.1 OR GPL-2.0-or-later OR LGPL-2.1-or-later
 *
 * cChardet uchardet overlay
 *
 * freedesktop uchardet's multibyte group decodes every candidate to Unicode
 * and fans those code points out to every generic language detector. cChardet
 * exposes only encoding and confidence, so this replacement keeps the charset
 * probers and their native confidence while skipping the generic language
 * pass. The upstream class ABI remains unchanged.
 */

#include <stdio.h>

#include "nsMBCSGroupProber.h"
#include "nsUniversalDetector.h"

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
            mProbers[i]->GetConfidence(0) > CANDIDATE_THRESHOLD)
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
          mProbers[i]->GetConfidence(0) > CANDIDATE_THRESHOLD)
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

    if (mIsActive[i])
      candidates[i][0] =
        (mProbers[i]->GetConfidence(0) > CANDIDATE_THRESHOLD);
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
      return mProbers[i]->GetConfidence(0);
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

using System.Collections.Generic;
using System.Runtime.InteropServices;
using Unity.Burst;
using Unity.Collections;
using Unity.Jobs;
using Unity.Mathematics;
using UnityEngine;

namespace Main.Character.AI
{
    public class AiFishManager : MonoBehaviour
    {
        private const int THREAD_GROUP_SIZE = 64;

        public static AiFishManager Instance;

        [SerializeField]
        private AiSimulationMode simulationMode = AiSimulationMode.CpuJob;

        [SerializeField]
        private ComputeShader fishAiCompute;

        [SerializeField]
        private RectTransform aiFishArea;

        [SerializeField]
        private PlayerCharacter playerCharacter;

        [SerializeField, ReadOnly]
        private List<Fish> fishList = new List<Fish>();
        public int FishCount => fishList.Count;

        private JobHandle jobHandle;
        private int computeKernelIndex = -1;
        private ComputeBuffer inputBuffer;
        private ComputeBuffer outputBuffer;
        private FishInputGpu[] inputCache;
        private FishOutputGpu[] outputCache;

        public const float VISION_RANGE = 5f;
        public const float VISION_ANGLE = 120f;

        public const float FOCUS_TARGET_DURATION = 2f;

        private void Awake()
        {
            Instance = this;

            if (fishAiCompute != null)
            {
                computeKernelIndex = fishAiCompute.FindKernel("CSMain");
            }
        }

        private void OnDestroy()
        {
            ReleaseGpuBuffers();
        }

        private void Update()
        {
            if (fishList.Count == 0)
                return;

            if (simulationMode == AiSimulationMode.HlslCompute)
            {
                UpdateHlslAi();
                return;
            }

            UpdateCpuAi();
        }

        private void UpdateCpuAi()
        {
            if (aiFishArea == null)
                return;

            var fishesCount = fishList.Count;
            var inputData = new NativeArray<FishJobInput>(fishesCount, Allocator.TempJob);
            var outputResults = new NativeArray<FishJobOutput>(fishesCount, Allocator.TempJob);

            // Get data
            for (int i = 0; i < fishesCount; i++)
            {
                // Fish Data
                var fish = fishList[i];
                var transform = fish.transform;
                var state = (int)State.Idle;
                var focusingTime = 0f;
                var targetPos = new float2(transform.position.x, transform.position.y);
                var isPlayer = fish is PlayerCharacter;

                // Get AI State if possible
                if (fish.TryGetComponent<AiFish>(out var aiFish))
                {
                    state = (int)aiFish.CurrentState;
                    focusingTime = aiFish.FocusingTime;
                    targetPos = new float2(aiFish.TargetPosition.x, aiFish.TargetPosition.y);
                }

                // Fill Input Data
                inputData[i] = new FishJobInput
                {
                    Index = i,
                    Position = new float2(transform.position.x, transform.position.y),
                    ForwardDirection = new float2(transform.right.x, transform.right.y),
                    CurrentTargetPosition = targetPos,
                    Size = fish.GetSize(),
                    CurrentStateInt = state,
                    FocusingTime = focusingTime,
                    IsPlayer = isPlayer,
                };
            }

            // Job Scheduling
            var aiJob = new FishAIJob
            {
                FishesInput = inputData,
                OutputResults = outputResults,
                MaxSearchDistance = VISION_RANGE * VISION_RANGE,
                MaxVisionAngle = math.cos(math.radians(VISION_ANGLE) / 2f),
                CurrentTime = Time.time,
                AreaCenter = new float2(aiFishArea.position.x, aiFishArea.position.y),
                AreaSize = new float2(aiFishArea.rect.width, aiFishArea.rect.height)
            };

            jobHandle = aiJob.Schedule(fishList.Count, jobHandle);

            // Wait for job
            jobHandle.Complete();

            // Apply
            for (int i = 0; i < fishList.Count; i++)
            {
                var fish = fishList[i];

                if (!fish.TryGetComponent<AiFish>(out var aiFish))
                    continue;

                var output = outputResults[i];
                aiFish.TargetPosition = output.TargetPosition;
                aiFish.CurrentState = (State)output.StateInt;
                aiFish.FocusingTime = output.FocusingTime;

                aiFish.UpdateMovement();
            }

            inputData.Dispose();
            outputResults.Dispose();
        }

        private void UpdateHlslAi()
        {
            if (fishAiCompute == null || computeKernelIndex < 0 || aiFishArea == null)
                return;

            EnsureGpuBuffers(fishList.Count);
            FillGpuInput();
            inputBuffer.SetData(inputCache);

            fishAiCompute.SetInt("FishCount", fishList.Count);
            fishAiCompute.SetFloat("CurrentTime", Time.time);
            fishAiCompute.SetFloat("MaxSearchDistanceSqr", VISION_RANGE * VISION_RANGE);
            fishAiCompute.SetFloat("MaxVisionCos", Mathf.Cos(Mathf.Deg2Rad * (VISION_ANGLE * 0.5f)));
            fishAiCompute.SetFloat("FocusTargetDuration", FOCUS_TARGET_DURATION);

            Vector2 areaCenter = aiFishArea.position;
            Vector2 areaSize = aiFishArea.rect.size;
            fishAiCompute.SetVector("AreaCenter", new Vector4(areaCenter.x, areaCenter.y, 0f, 0f));
            fishAiCompute.SetVector("AreaSize", new Vector4(areaSize.x, areaSize.y, 0f, 0f));

            fishAiCompute.SetBuffer(computeKernelIndex, "InputFishes", inputBuffer);
            fishAiCompute.SetBuffer(computeKernelIndex, "OutputFishes", outputBuffer);

            int groupCount = Mathf.CeilToInt(fishList.Count / (float)THREAD_GROUP_SIZE);
            fishAiCompute.Dispatch(computeKernelIndex, groupCount, 1, 1);

            outputBuffer.GetData(outputCache);
            ApplyGpuOutput();
        }

        private void FillGpuInput()
        {
            for (int i = 0; i < fishList.Count; i++)
            {
                Fish fish = fishList[i];
                Transform fishTransform = fish.transform;

                int state = (int)State.Idle;
                float focusingTime = 0f;
                Vector2 targetPosition = fishTransform.position;

                if (fish.TryGetComponent<AiFish>(out var aiFish))
                {
                    state = (int)aiFish.CurrentState;
                    focusingTime = aiFish.FocusingTime;
                    targetPosition = new Vector2(aiFish.TargetPosition.x, aiFish.TargetPosition.y);
                }

                Vector2 position = fishTransform.position;
                Vector2 forward = fishTransform.right;
                if (forward.sqrMagnitude > 0f)
                {
                    forward.Normalize();
                }

                inputCache[i] = new FishInputGpu
                {
                    PositionForward = new Vector4(position.x, position.y, forward.x, forward.y),
                    TargetSizeState = new Vector4(targetPosition.x, targetPosition.y, fish.GetSize(), state),
                    FocusPlayerIndex = new Vector4(focusingTime, fish is PlayerCharacter ? 1f : 0f, i, 0f),
                };
            }
        }

        private void ApplyGpuOutput()
        {
            for (int i = 0; i < fishList.Count; i++)
            {
                if (!fishList[i].TryGetComponent<AiFish>(out var aiFish))
                    continue;

                FishOutputGpu output = outputCache[i];
                Vector4 value = output.TargetStateFocus;

                aiFish.TargetPosition = new float2(value.x, value.y);
                aiFish.CurrentState = (State)Mathf.RoundToInt(value.z);
                aiFish.FocusingTime = value.w;
                aiFish.UpdateMovement();
            }
        }

        private void EnsureGpuBuffers(int fishCount)
        {
            bool rebuild =
                inputBuffer == null ||
                outputBuffer == null ||
                inputCache == null ||
                outputCache == null ||
                inputCache.Length != fishCount;

            if (!rebuild)
                return;

            ReleaseGpuBuffers();

            inputCache = new FishInputGpu[fishCount];
            outputCache = new FishOutputGpu[fishCount];

            inputBuffer = new ComputeBuffer(fishCount, Marshal.SizeOf<FishInputGpu>());
            outputBuffer = new ComputeBuffer(fishCount, Marshal.SizeOf<FishOutputGpu>());
        }

        private void ReleaseGpuBuffers()
        {
            inputBuffer?.Release();
            outputBuffer?.Release();
            inputBuffer = null;
            outputBuffer = null;
        }

        public void FetchAllFish()
        {
            fishList.Clear();

            // Add Player
            var playerCharacter = FindAnyObjectByType<PlayerCharacter>();
            fishList.Add(playerCharacter);
            playerCharacter.OnDeath += () => fishList.Remove(playerCharacter);

            // Add AI Fishes
            var aiFishes = FindObjectsByType<AiFish>(sortMode: FindObjectsSortMode.None);
            foreach (var aiFish in aiFishes)
            {
                fishList.Add(aiFish);
                aiFish.OnDeath += () => fishList.Remove(aiFish);
            }

            Debug.Log($"[AiFishManager] Fetched {aiFishes.Length} Fishes.");
        }

        private void OnDrawGizmos()
        {
            if (aiFishArea == null)
                return;

            Gizmos.color = Color.cyan;
            Gizmos.DrawWireCube(aiFishArea.position, new Vector3(aiFishArea.rect.width, aiFishArea.rect.height, 1f));
        }
    }

    public enum State
    {
        Idle = 0,
        Hunting = 1,
        Fleeing = 2,
    }

    public enum AiSimulationMode
    {
        CpuJob = 0,
        HlslCompute = 1,
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct FishInputGpu
    {
        public Vector4 PositionForward;
        public Vector4 TargetSizeState;
        public Vector4 FocusPlayerIndex;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct FishOutputGpu
    {
        public Vector4 TargetStateFocus;
    }

    public struct FishJobInput
    {
        public int Index;
        public float2 Position;
        public float2 ForwardDirection;
        public float2 CurrentTargetPosition;
        public float Size;
        public int CurrentStateInt;
        public float FocusingTime;
        public bool IsPlayer;
    }

    public struct FishJobOutput
    {
        public float2 TargetPosition;
        public int StateInt; // For Job
        public float FocusingTime;
    }

    [BurstCompile]
    public struct FishAIJob : IJobFor
    {
        // Input
        [ReadOnly]
        public NativeArray<FishJobInput> FishesInput;

        [ReadOnly]
        public float MaxSearchDistance;

        [ReadOnly]
        public float MaxVisionAngle;

        [ReadOnly]
        public float CurrentTime;

        [ReadOnly]
        public float2 AreaCenter;

        [ReadOnly]
        public float2 AreaSize;

        // Output
        [WriteOnly]
        public NativeArray<FishJobOutput> OutputResults;

        public void Execute(int index)
        {
            // Self
            var ownInput = FishesInput[index];
            var ownSize = ownInput.Size;
            var ownPosition = ownInput.Position;
            var closestTarget = MaxSearchDistance;

            // Target
            var newTargetPos = ownInput.CurrentTargetPosition;
            var newState = ownInput.CurrentStateInt;

            var isFoundTarget = false;
            var focusingTime = ownInput.FocusingTime;

            // Priority targets: player first for all hunters, but aggressive prioritizes more
            float2 playerTargetPos = float2.zero;
            float playerDistance = MaxSearchDistance;
            bool foundPlayer = false;
            float2 closestPreyPos = float2.zero;
            float closestPreyDistance = MaxSearchDistance;

            // Find target - prioritize player first
            for (int i = 0; i < FishesInput.Length; i++)
            {
                // Skip self
                if (i == index)
                    continue;

                var otherFish = FishesInput[i];
                var distance = math.lengthsq(otherFish.Position - ownPosition);

                // Out of Vision Range
                if (distance > MaxSearchDistance)
                    continue;

                // Out of Vision Cone
                if (!IsInVisionCone(ownPosition, ownInput.ForwardDirection, otherFish.Position, MaxVisionAngle))
                    continue;

                // Check if target is player - prioritize player first for all hunters
                if (otherFish.IsPlayer && otherFish.Size < ownSize)
                {
                    playerTargetPos = otherFish.Position;
                    playerDistance = distance;
                    foundPlayer = true;
                }

                // Found Prey (non-player)
                if (!otherFish.IsPlayer && otherFish.Size < ownSize)
                {
                    if (distance < closestPreyDistance)
                    {
                        closestPreyPos = otherFish.Position;
                        closestPreyDistance = distance;
                    }
                }

                // Found Predator
                else if (otherFish.Size > ownSize)
                {
                    // Fleeing
                    if (distance < closestTarget * 1.5f || newState != (int)State.Fleeing)
                    {
                        var fleeDir = math.normalize(ownPosition - otherFish.Position);
                        newTargetPos = ownPosition + fleeDir * 20;
                        newState = (int)State.Fleeing;
                        closestTarget = distance;
                        isFoundTarget = true;

                        focusingTime = CurrentTime + AiFishManager.FOCUS_TARGET_DURATION;
                    }
                }
            }

            // Apply target: prioritize player first for all hunters
            if (foundPlayer)
            {
                newTargetPos = playerTargetPos;
                newState = (int)State.Hunting;
                isFoundTarget = true;
                focusingTime = CurrentTime + AiFishManager.FOCUS_TARGET_DURATION;
            }
            else if (closestPreyDistance < MaxSearchDistance)
            {
                // Hunt closest prey if no player found
                newTargetPos = closestPreyPos;
                newState = (int)State.Hunting;
                isFoundTarget = true;
                focusingTime = CurrentTime + AiFishManager.FOCUS_TARGET_DURATION;
            }

            // Check if current hunt target is out of bounds - return to center as priority
            if (newState == (int)State.Hunting && isFoundTarget)
            {
                bool isHuntTargetOutOfBounds =
                    math.abs(newTargetPos.x - AreaCenter.x) > AreaSize.x / 2f ||
                    math.abs(newTargetPos.y - AreaCenter.y) > AreaSize.y / 2f;

                if (isHuntTargetOutOfBounds)
                {
                    // Return to center as priority
                    newTargetPos = AreaCenter;
                    newState = (int)State.Idle;
                    isFoundTarget = true;
                    focusingTime = 0f;
                }
            }

            // No target
            if (!isFoundTarget)
            {
                // Check bounds
                bool isOutOfBounds =
                    math.abs(ownPosition.x - AreaCenter.x) > AreaSize.x / 2f ||
                    math.abs(ownPosition.y - AreaCenter.y) > AreaSize.y / 2f;

                if (isOutOfBounds && newState != (int)State.Hunting && newState != (int)State.Fleeing)
                {
                    // Return to center
                    newTargetPos = AreaCenter;
                    newState = (int)State.Idle;
                    isFoundTarget = true;
                    focusingTime = 0f;
                }

                switch (newState)
                {
                    case (int)State.Fleeing:
                        if (CurrentTime >= focusingTime)
                        {
                            newState = (int)State.Idle;
                            focusingTime = 0f;
                        }
                        else
                        {
                            // Keep moving to target
                            isFoundTarget = true;
                            newTargetPos = ownPosition + ownInput.ForwardDirection * 20f;
                        }
                        break;

                    case (int)State.Hunting:
                        if (CurrentTime >= focusingTime)
                        {
                            newState = (int)State.Idle;
                            focusingTime = 0f;
                        }
                        else
                        {
                            // Keep moving to target
                            isFoundTarget = true;
                            newTargetPos = ownPosition + ownInput.ForwardDirection * 20f;
                        }
                        break;

                    case (int)State.Idle:

                        // Check if target is valid (in bounds) and if we reached it
                        bool isTargetOutOfBounds =
                            math.abs(newTargetPos.x - AreaCenter.x) > AreaSize.x / 2f ||
                            math.abs(newTargetPos.y - AreaCenter.y) > AreaSize.y / 2f;

                        float dist = math.distance(ownPosition, newTargetPos);

                        if (dist < 2f || isTargetOutOfBounds)
                        {
                            // Random Wandering Position
                            var randomSeed = (uint)((ownInput.Index * 1000f) + (ownPosition.x * 100) + (ownPosition.y * 100) + (CurrentTime * 1000));
                            Unity.Mathematics.Random random = new Unity.Mathematics.Random(randomSeed);

                            var halfSize = AreaSize / 2f;
                            newTargetPos.x = random.NextFloat(AreaCenter.x - halfSize.x, AreaCenter.x + halfSize.x);
                            newTargetPos.y = random.NextFloat(AreaCenter.y - halfSize.y, AreaCenter.y + halfSize.y);
                        }
                        newState = (int)State.Idle;
                        break;
                }
            }

            // Write output
            OutputResults[index] = new FishJobOutput
            {
                TargetPosition = newTargetPos,
                StateInt = newState,
                FocusingTime = focusingTime,
            };
        }

        private static bool IsInVisionCone(float2 ownPos, float2 ownForward, float2 targetPos, float cosAngleThreshold)
        {
            float2 directionToTarget = math.normalize(targetPos - ownPos);
            float dotProduct = math.dot(ownForward, directionToTarget);

            // If the dot product is greater than the cosine of the half-angle, the target is in the cone.
            return dotProduct >= cosAngleThreshold;
        }
    }
}
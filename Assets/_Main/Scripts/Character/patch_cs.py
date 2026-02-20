import os

file_path = "/Users/jirawatdamung/Downloads/_Unity Project/TINYTUNA/Assets/_Main/Scripts/Character/AiFishManager.cs"
with open(file_path, "r") as f:
    content = f.read()

# Replace FishCount tracking
content = content.replace(
    "[SerializeField, ReadOnly]\n        private List<Fish> fishList = new List<Fish>();\n        public int FishCount => fishList.Count;",
    "[SerializeField, ReadOnly]\n        private List<Fish> fishList = new List<Fish>();\n        private FishCache[] fishCacheArray = new FishCache[0];\n        public int FishCount => fishCacheArray.Length;"
)

# Replace Update
old_update = """        private void Update()
        {
            if (fishList.Count == 0)
                return;

            GetActiveAreaBounds(out Vector2 activeCenter, out Vector2 activeExtents);

            // Toggle active state for fish outside the active area
            for (int i = 0; i < fishList.Count; i++)
            {
                var fish = fishList[i];
                if (fish == null) continue;

                if (fish is PlayerCharacter)
                    continue;

                Vector2 pos = fish.transform.position;
                Vector2 diff = new Vector2(Mathf.Abs(pos.x - activeCenter.x), Mathf.Abs(pos.y - activeCenter.y));
                bool inActiveArea = diff.x <= activeExtents.x && diff.y <= activeExtents.y;

                if (fish.gameObject.activeSelf != inActiveArea)
                {
                    fish.gameObject.SetActive(inActiveArea);
                }
            }

            if (simulationMode == AiSimulationMode.HlslCompute)
            {
                UpdateHlslAi(activeCenter, activeExtents);
                return;
            }
            if (simulationMode == AiSimulationMode.RustNative)
            {
                UpdateRustAi(activeCenter, activeExtents);
                return;
            }

            UpdateCpuAi(activeCenter, activeExtents);
        }"""
new_update = """        private void Update()
        {
            if (fishCacheArray.Length == 0)
                return;

            GetActiveAreaBounds(out Vector2 activeCenter, out Vector2 activeExtents);

            if (simulationMode == AiSimulationMode.HlslCompute)
            {
                UpdateHlslAi(activeCenter, activeExtents);
                return;
            }
            if (simulationMode == AiSimulationMode.RustNative)
            {
                UpdateRustAi(activeCenter, activeExtents);
                return;
            }

            UpdateCpuAi(activeCenter, activeExtents);
        }"""
content = content.replace(old_update, new_update)

# Replace UpdateRustAi
old_rust = """        private void UpdateRustAi(Vector2 activeCenter, Vector2 activeExtents)
        {
            if (aiFishArea == null)
                return;

            var fishesCount = fishList.Count;

            if (rustInputCache == null || rustInputCache.Length < fishesCount)
            {
                int newSize = Mathf.Max(fishesCount, rustInputCache?.Length * 2 ?? 256);
                rustInputCache = new FishJobInput[newSize];
                rustOutputCache = new FishJobOutput[newSize];
            }

            // Get data
            for (int i = 0; i < fishesCount; i++)
            {
                var fish = fishList[i];
                var transform = fish.transform;
                var state = (int)State.Idle;
                var focusingTime = 0f;
                var targetPos = new float2(transform.position.x, transform.position.y);
                var isPlayer = fish is PlayerCharacter;

                if (fish.TryGetComponent<AiFish>(out var aiFish))
                {
                    state = (int)aiFish.CurrentState;
                    focusingTime = aiFish.FocusingTime;
                    targetPos = new float2(aiFish.TargetPosition.x, aiFish.TargetPosition.y);
                }

                rustInputCache[i] = new FishJobInput
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

            // Call Rust
            process_fish_ai(
                rustInputCache,
                rustOutputCache,
                fishesCount,
                VISION_RANGE * VISION_RANGE,
                math.cos(math.radians(VISION_ANGLE) / 2f),
                Time.time,
                new float2(aiFishArea.position.x, aiFishArea.position.y),
                new float2(aiFishArea.rect.width, aiFishArea.rect.height),
                new float2(activeCenter.x, activeCenter.y),
                new float2(activeExtents.x, activeExtents.y)
            );

            // Apply
            for (int i = 0; i < fishesCount; i++)
            {
                var fish = fishList[i];

                if (!fish.TryGetComponent<AiFish>(out var aiFish))
                    continue;

                var output = rustOutputCache[i];
                aiFish.TargetPosition = output.TargetPosition;
                aiFish.CurrentState = (State)output.StateInt;
                aiFish.FocusingTime = output.FocusingTime;

                aiFish.UpdateMovement();
            }
        }"""
new_rust = """        private void UpdateRustAi(Vector2 activeCenter, Vector2 activeExtents)
        {
            if (aiFishArea == null)
                return;

            var fishesCount = fishCacheArray.Length;

            if (rustInputCache == null || rustInputCache.Length < fishesCount)
            {
                int newSize = Mathf.Max(fishesCount, rustInputCache?.Length * 2 ?? 256);
                rustInputCache = new FishJobInput[newSize];
                rustOutputCache = new FishJobOutput[newSize];
            }

            // Get data
            for (int i = 0; i < fishesCount; i++)
            {
                var cache = fishCacheArray[i];
                var transform = cache.Transform;
                
                var state = (int)State.Idle;
                var focusingTime = 0f;
                var pos = transform.position;
                var right = transform.right;
                var targetPos = new float2(pos.x, pos.y);

                if (cache.AiFish != null)
                {
                    state = (int)cache.AiFish.CurrentState;
                    focusingTime = cache.AiFish.FocusingTime;
                    targetPos = new float2(cache.AiFish.TargetPosition.x, cache.AiFish.TargetPosition.y);
                }

                rustInputCache[i] = new FishJobInput
                {
                    Index = i,
                    Position = new float2(pos.x, pos.y),
                    ForwardDirection = new float2(right.x, right.y),
                    CurrentTargetPosition = targetPos,
                    Size = cache.Size,
                    CurrentStateInt = state,
                    FocusingTime = focusingTime,
                    IsPlayer = cache.IsPlayer,
                };
            }

            // Call Rust
            process_fish_ai(
                rustInputCache,
                rustOutputCache,
                fishesCount,
                VISION_RANGE * VISION_RANGE,
                math.cos(math.radians(VISION_ANGLE) / 2f),
                Time.time,
                new float2(aiFishArea.position.x, aiFishArea.position.y),
                new float2(aiFishArea.rect.width, aiFishArea.rect.height),
                new float2(activeCenter.x, activeCenter.y),
                new float2(activeExtents.x, activeExtents.y)
            );

            // Apply
            for (int i = 0; i < fishesCount; i++)
            {
                var cache = fishCacheArray[i];

                if (cache.AiFish == null)
                    continue;

                var output = rustOutputCache[i];
                cache.AiFish.TargetPosition = output.TargetPosition;
                cache.AiFish.CurrentState = (State)output.StateInt;
                cache.AiFish.FocusingTime = output.FocusingTime;

                cache.AiFish.UpdateMovement();
            }
        }"""
content = content.replace(old_rust, new_rust)

# Replace UpdateCpuAi
old_cpu = """        private void UpdateCpuAi(Vector2 activeCenter, Vector2 activeExtents)
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
                AreaSize = new float2(aiFishArea.rect.width, aiFishArea.rect.height),
                ActiveAreaCenter = activeCenter,
                ActiveAreaExtents = activeExtents
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
        }"""
new_cpu = """        private void UpdateCpuAi(Vector2 activeCenter, Vector2 activeExtents)
        {
            if (aiFishArea == null)
                return;

            var fishesCount = fishCacheArray.Length;
            var inputData = new NativeArray<FishJobInput>(fishesCount, Allocator.TempJob);
            var outputResults = new NativeArray<FishJobOutput>(fishesCount, Allocator.TempJob);

            // Get data
            for (int i = 0; i < fishesCount; i++)
            {
                var cache = fishCacheArray[i];
                var transform = cache.Transform;
                
                var state = (int)State.Idle;
                var focusingTime = 0f;
                var pos = transform.position;
                var right = transform.right;
                var targetPos = new float2(pos.x, pos.y);

                if (cache.AiFish != null)
                {
                    state = (int)cache.AiFish.CurrentState;
                    focusingTime = cache.AiFish.FocusingTime;
                    targetPos = new float2(cache.AiFish.TargetPosition.x, cache.AiFish.TargetPosition.y);
                }

                inputData[i] = new FishJobInput
                {
                    Index = i,
                    Position = new float2(pos.x, pos.y),
                    ForwardDirection = new float2(right.x, right.y),
                    CurrentTargetPosition = targetPos,
                    Size = cache.Size,
                    CurrentStateInt = state,
                    FocusingTime = focusingTime,
                    IsPlayer = cache.IsPlayer,
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
                AreaSize = new float2(aiFishArea.rect.width, aiFishArea.rect.height),
                ActiveAreaCenter = activeCenter,
                ActiveAreaExtents = activeExtents
            };

            jobHandle = aiJob.Schedule(fishesCount, jobHandle);

            // Wait for job
            jobHandle.Complete();

            // Apply
            for (int i = 0; i < fishesCount; i++)
            {
                var cache = fishCacheArray[i];

                if (cache.AiFish == null)
                    continue;

                var output = outputResults[i];
                cache.AiFish.TargetPosition = output.TargetPosition;
                cache.AiFish.CurrentState = (State)output.StateInt;
                cache.AiFish.FocusingTime = output.FocusingTime;

                cache.AiFish.UpdateMovement();
            }

            inputData.Dispose();
            outputResults.Dispose();
        }"""
content = content.replace(old_cpu, new_cpu)

# Replace Hlsl
old_hlsl = """        private void UpdateHlslAi(Vector2 activeCenter, Vector2 activeExtents)
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
            fishAiCompute.SetVector("AreaCenter", new Vector4(areaCenter.x, areaCenter.y, activeCenter.x, activeCenter.y));
            fishAiCompute.SetVector("AreaSize", new Vector4(areaSize.x, areaSize.y, activeExtents.x, activeExtents.y));

            fishAiCompute.SetBuffer(computeKernelIndex, "InputFishes", inputBuffer);
            fishAiCompute.SetBuffer(computeKernelIndex, "OutputFishes", outputBuffer);

            int groupCount = Mathf.CeilToInt(fishList.Count / (float)THREAD_GROUP_SIZE);
            fishAiCompute.Dispatch(computeKernelIndex, groupCount, 1, 1);

            outputBuffer.GetData(outputCache);
            ApplyGpuOutput();
        }"""
new_hlsl = """        private void UpdateHlslAi(Vector2 activeCenter, Vector2 activeExtents)
        {
            if (fishAiCompute == null || computeKernelIndex < 0 || aiFishArea == null)
                return;

            EnsureGpuBuffers(fishCacheArray.Length);
            FillGpuInput();
            inputBuffer.SetData(inputCache);

            fishAiCompute.SetInt("FishCount", fishCacheArray.Length);
            fishAiCompute.SetFloat("CurrentTime", Time.time);
            fishAiCompute.SetFloat("MaxSearchDistanceSqr", VISION_RANGE * VISION_RANGE);
            fishAiCompute.SetFloat("MaxVisionCos", Mathf.Cos(Mathf.Deg2Rad * (VISION_ANGLE * 0.5f)));
            fishAiCompute.SetFloat("FocusTargetDuration", FOCUS_TARGET_DURATION);

            Vector2 areaCenter = aiFishArea.position;
            Vector2 areaSize = aiFishArea.rect.size;
            fishAiCompute.SetVector("AreaCenter", new Vector4(areaCenter.x, areaCenter.y, activeCenter.x, activeCenter.y));
            fishAiCompute.SetVector("AreaSize", new Vector4(areaSize.x, areaSize.y, activeExtents.x, activeExtents.y));

            fishAiCompute.SetBuffer(computeKernelIndex, "InputFishes", inputBuffer);
            fishAiCompute.SetBuffer(computeKernelIndex, "OutputFishes", outputBuffer);

            int groupCount = Mathf.CeilToInt(fishCacheArray.Length / (float)THREAD_GROUP_SIZE);
            fishAiCompute.Dispatch(computeKernelIndex, groupCount, 1, 1);

            outputBuffer.GetData(outputCache);
            ApplyGpuOutput();
        }"""
content = content.replace(old_hlsl, new_hlsl)

old_gpu1 = """        private void FillGpuInput()
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
        }"""

new_gpu1 = """        private void FillGpuInput()
        {
            for (int i = 0; i < fishCacheArray.Length; i++)
            {
                var cache = fishCacheArray[i];
                Transform fishTransform = cache.Transform;

                int state = (int)State.Idle;
                float focusingTime = 0f;
                Vector2 targetPosition = fishTransform.position;

                if (cache.AiFish != null)
                {
                    state = (int)cache.AiFish.CurrentState;
                    focusingTime = cache.AiFish.FocusingTime;
                    targetPosition = new Vector2(cache.AiFish.TargetPosition.x, cache.AiFish.TargetPosition.y);
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
                    TargetSizeState = new Vector4(targetPosition.x, targetPosition.y, cache.Size, state),
                    FocusPlayerIndex = new Vector4(focusingTime, cache.IsPlayer ? 1f : 0f, i, 0f),
                };
            }
        }"""
content = content.replace(old_gpu1, new_gpu1)

old_gpu2 = """        private void ApplyGpuOutput()
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
        }"""

new_gpu2 = """        private void ApplyGpuOutput()
        {
            for (int i = 0; i < fishCacheArray.Length; i++)
            {
                var cache = fishCacheArray[i];
                if (cache.AiFish == null)
                    continue;

                FishOutputGpu output = outputCache[i];
                Vector4 value = output.TargetStateFocus;

                cache.AiFish.TargetPosition = new float2(value.x, value.y);
                cache.AiFish.CurrentState = (State)Mathf.RoundToInt(value.z);
                cache.AiFish.FocusingTime = value.w;
                cache.AiFish.UpdateMovement();
            }
        }"""
content = content.replace(old_gpu2, new_gpu2)

old_fetch = """        public void FetchAllFish()
        {
            fishList.Clear();

            // Add Player
            var playerCharacter = FindAnyObjectByType<PlayerCharacter>(FindObjectsInactive.Include);
            if (playerCharacter != null)
            {
                fishList.Add(playerCharacter);
                playerCharacter.OnDeath += () => fishList.Remove(playerCharacter);
            }

            // Add AI Fishes
            var aiFishes = FindObjectsByType<AiFish>(FindObjectsInactive.Include, sortMode: FindObjectsSortMode.None);
            foreach (var aiFish in aiFishes)
            {
                fishList.Add(aiFish);
                aiFish.OnDeath += () => fishList.Remove(aiFish);
            }

            Debug.Log($"[AiFishManager] Fetched {aiFishes.Length} Fishes.");
        }"""

new_fetch = """        public void FetchAllFish()
        {
            fishList.Clear();

            // Add Player
            var playerCharacter = FindAnyObjectByType<PlayerCharacter>(FindObjectsInactive.Include);
            if (playerCharacter != null)
            {
                fishList.Add(playerCharacter);
                playerCharacter.OnDeath += () => 
                {
                    fishList.Remove(playerCharacter);
                    BuildFishCache();
                };
            }

            // Add AI Fishes
            var aiFishes = FindObjectsByType<AiFish>(FindObjectsInactive.Include, sortMode: FindObjectsSortMode.None);
            foreach (var aiFish in aiFishes)
            {
                fishList.Add(aiFish);
                aiFish.OnDeath += () => 
                {
                    fishList.Remove(aiFish);
                    BuildFishCache();
                };
            }
            
            BuildFishCache();

            Debug.Log($"[AiFishManager] Fetched {aiFishes.Length} Fishes.");
        }

        private void BuildFishCache()
        {
            fishCacheArray = new FishCache[fishList.Count];
            for (int i = 0; i < fishList.Count; i++)
            {
                var f = fishList[i];
                var aiFish = f as AiFish;
                fishCacheArray[i] = new FishCache
                {
                    Fish = f,
                    AiFish = aiFish,
                    Transform = f.transform,
                    IsPlayer = f is PlayerCharacter,
                    Size = f.GetSize()
                };
            }
        }"""
content = content.replace(old_fetch, new_fetch)

# In definition around bottom, add struct
old_struct = """    public struct FishJobOutput
    {
        public float2 TargetPosition;
        public int StateInt; // For Job
        public float FocusingTime;
    }"""
new_struct = """    public struct FishJobOutput
    {
        public float2 TargetPosition;
        public int StateInt; // For Job
        public float FocusingTime;
    }

    public struct FishCache
    {
        public Fish Fish;
        public AiFish AiFish;
        public Transform Transform;
        public bool IsPlayer;
        public float Size;
    }"""
content = content.replace(old_struct, new_struct)

with open(file_path, "w") as f:
    f.write(content)


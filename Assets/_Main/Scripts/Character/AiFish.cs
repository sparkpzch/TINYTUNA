using NaughtyAttributes;
using Unity.Mathematics;
using UnityEngine;

namespace Main.Character.AI
{
    public class AiFish : Fish
    {
        [ReadOnly]
        public State CurrentState;

        [ReadOnly]
        public float2 TargetPosition;

        [ReadOnly]
        public float FocusingTime;

        protected override void FixedUpdate()
        {
            base.FixedUpdate();
            UpdateMovement();
            if (math.lengthsq(moveDir) < 0.001f)
            {
                Rb2d.linearVelocity = UnityEngine.Vector2.zero;
            }
            else
            {
                Move(moveDir, UnityEngine.ForceMode2D.Force, multiplier: 0.25f);
            }
        }

        // Movement is handled on the main thread, consuming the Job's calculated target
        public void UpdateMovement()
        {
            float2 currentPos = new float2(transform.position.x, transform.position.y);
            float2 direction = TargetPosition - currentPos;
            moveDir = math.normalizesafe(direction);
        }

        protected override void Eat(Fish targetFish)
        {
            base.Eat(targetFish);
            CurrentState = State.Idle;
            FocusingTime = 0f;
        }

        private void OnDrawGizmos()
        {
            // Draw fish state
            switch (CurrentState)
            {
                case State.Idle:
                    Gizmos.color = Color.green;
                    break;

                case State.Hunting:
                    Gizmos.color = Color.red;
                    break;

                case State.Fleeing:
                    Gizmos.color = Color.yellow;
                    break;

                default:
                    Gizmos.color = Color.white;
                    break;
            }
            Gizmos.DrawWireSphere(transform.position, GetSize());


            // Draw velocity
            Gizmos.color = Color.orange;
            Gizmos.DrawLine(transform.position, transform.position + new Vector3(Rb2d.linearVelocity.x, Rb2d.linearVelocity.y, 0));
        }

        private void OnDrawGizmosSelected()
        {
            if (mouthPos != default)
            {
                Gizmos.DrawWireSphere(mouthPos.position, mouthSizeSqr);
            }

            // Draw target position
            Gizmos.color = Color.softRed;
            Gizmos.DrawLine(transform.position, new Vector3(TargetPosition.x, TargetPosition.y, 0));
            Gizmos.DrawWireSphere(new Vector3(TargetPosition.x, TargetPosition.y, 0), 0.05f);

            // Draw vision cone
            DrawVisionCone(transform.position, transform.right, AiFishManager.VISION_RANGE, AiFishManager.VISION_ANGLE, Color.cyan);
        }
        private void DrawVisionCone(Vector3 origin, Vector3 forward, float range, float angle, Color color)
        {
            var segments = 10;
            Gizmos.color = color;

            // Normalize the 2D forward vector (assuming XY plane)
            Vector3 forward2D = new Vector3(forward.x, forward.y, 0).normalized;

            // Calculate the half angle
            float halfAngle = angle / 2f;

            // Determine the starting and ending angles for the arc
            // The forward vector is at 0 degrees relative to itself for these calculations.
            // If transform.up is (0,1,0), then -halfAngle will be to the left, +halfAngle to the right.
            float startAngle = -halfAngle;
            float endAngle = halfAngle;

            // Cache the previous point for drawing segments
            Vector3 previousPoint = Vector3.zero;

            for (int i = 0; i <= segments; i++)
            {
                // Interpolate angle from start to end
                float currentAngle = Mathf.Lerp(startAngle, endAngle, (float)i / segments);

                // Rotate the forward vector by the current angle around the Z-axis (for 2D)
                Quaternion rotation = Quaternion.AngleAxis(currentAngle, Vector3.forward);
                Vector3 rayDirection = rotation * forward2D;

                // Calculate the point on the arc
                Vector3 currentPoint = origin + rayDirection * range;

                if (i == 0)
                {
                    // Draw the first boundary line from origin to the start of the arc
                    Gizmos.DrawLine(origin, currentPoint);
                }
                else
                {
                    // Draw segments of the arc
                    Gizmos.DrawLine(previousPoint, currentPoint);
                }

                if (i == segments)
                {
                    // Draw the last boundary line from origin to the end of the arc
                    Gizmos.DrawLine(origin, currentPoint);
                }

                previousPoint = currentPoint;
            }
        }
    }
}
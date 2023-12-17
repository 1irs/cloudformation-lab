from troposphere import (
    Template,
    Parameter,
    Output,
    Ref,
    GetAtt,
    Join,
    Sub,
    Region,
    Retain,
)
from troposphere.ec2 import SecurityGroup
from troposphere.rds import DBInstance
from troposphere import ecs
from troposphere.ecs import NetworkConfiguration, AwsvpcConfiguration
from troposphere.logs import LogGroup
from troposphere.iam import Role

DB_USER = "admin"
DB_PASSWORD = "StrongPassword1#"
DB_NAME = "wordpress"

# CloudFormation-шаблон
t = Template()

vpc_id_param = Parameter(
    "VPCId",
    Description="VPC",
    Type="AWS::EC2::VPC::Id",
)
t.add_parameter(vpc_id_param)

db_sgr = SecurityGroup(
    title="DBSecurityGroup",
    GroupDescription="DB Security Group",
    GroupName="DB Security Group",
    SecurityGroupIngress=[
        dict(IpProtocol="tcp", FromPort="3306", ToPort="3306", CidrIp="0.0.0.0/0")
    ],
    VpcId=vpc_id_param.ref(),
)
t.add_resource(db_sgr)

db = DBInstance(
    title="Database",
    AllocatedStorage="20",
    DBInstanceClass="db.t3.micro",
    DBName=DB_NAME,
    Engine="mysql",
    EngineVersion="8.0.35",
    PubliclyAccessible=True,
    MasterUsername=DB_USER,
    MasterUserPassword=DB_PASSWORD,
    VPCSecurityGroups=[db_sgr.ref()],
    StorageType="gp2",
)
t.add_resource(db)

subnet_id_param = Parameter(
    "SubnetId",
    Description="Subnet",
    Type="AWS::EC2::Subnet::Id",
)
t.add_parameter(subnet_id_param)

web_security_group = SecurityGroup(
    title="WebSecurityGroup",
    GroupDescription="Web Security Group",
    GroupName="Web Security Group",
    SecurityGroupIngress=[
        dict(IpProtocol="tcp", FromPort="80", ToPort="80", CidrIp="0.0.0.0/0")
    ],
    VpcId=vpc_id_param.ref(),
)
t.add_resource(web_security_group)

execution_role = Role(
    title="EcsTaskExecutionRole",
    AssumeRolePolicyDocument={
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    },
    ManagedPolicyArns=[
        "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
    ],
)
t.add_resource(execution_role)

ecs_cluster = ecs.Cluster(
    title="ECSCluster", CapacityProviders=["FARGATE"], DependsOn=execution_role
)
t.add_resource(ecs_cluster)

log_group = LogGroup(
    title="WebLogGroup",
    LogGroupName=Sub("/ecs/web-${AWS::StackName}"),
    RetentionInDays=30,
)
t.add_resource(log_group)


ecs_task_definition = ecs.TaskDefinition(
    title="ECSTaskDefinition",
    Cpu="256",
    Memory="512",
    NetworkMode="awsvpc",
    Family="wordpress",
    ExecutionRoleArn=execution_role.ref(),
    RuntimePlatform=ecs.RuntimePlatform(
        CpuArchitecture="X86_64", OperatingSystemFamily="LINUX"
    ),
    ContainerDefinitions=[
        ecs.ContainerDefinition(
            LogConfiguration=ecs.LogConfiguration(
                Options={
                    "awslogs-group": log_group.ref(),
                    "awslogs-region": "us-west-1",
                    "awslogs-stream-prefix": "ecs",
                },
                LogDriver="awslogs",
            ),
            Name="wordpress",
            Image="wordpress",
            MemoryReservation=256,
            PortMappings=[
                ecs.PortMapping(ContainerPort=80, HostPort=80, Protocol="tcp")
            ],
            Environment=[
                ecs.Environment(Name="WORDPRESS_DB_HOST", Value=GetAtt(db, "Endpoint.Address")),
                ecs.Environment(Name="WORDPRESS_DB_USER", Value=DB_USER),
                ecs.Environment(Name="WORDPRESS_DB_PASSWORD", Value=DB_PASSWORD),
                ecs.Environment(Name="WORDPRESS_DEBUG", Value="1"),
            ],
            Essential=True,
            Cpu=0,
        )
    ],
)
t.add_resource(ecs_task_definition)

ecs_service = ecs.Service(
    title="ECSService",
    DesiredCount=1,
    LaunchType="FARGATE",
    NetworkConfiguration=NetworkConfiguration(
        AwsvpcConfiguration=AwsvpcConfiguration(
            AssignPublicIp="ENABLED",
            Subnets=[subnet_id_param.ref()],
            SecurityGroups=[web_security_group.ref()],
        )
    ),
    PlatformVersion="LATEST",
    Cluster=ecs_cluster.ref(),
    TaskDefinition=ecs_task_definition.ref(),
)
t.add_resource(ecs_service)

with open("lab-template.json", "w") as f:
    f.write(t.to_json())
